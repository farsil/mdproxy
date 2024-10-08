#!/usr/bin/env python

from dataclasses import dataclass, asdict
from fnmatch import filter as fnfilter
from glob import glob
from hashlib import md5
from io import BytesIO, TextIOWrapper
import json
import logging
from os import path, makedirs, unlink
import sys
from typing import Iterable, Tuple
from urllib.request import urlopen
from urllib.parse import quote as urlquote
from zipfile import ZipFile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigSource:
    url: str
    entries: list[str]
    renames: dict[str, str]

    @classmethod
    def from_dict(cls: "ConfigSource", d: dict) -> "ConfigSource":
        return cls(
            url=d["url"],
            entries=d["entries"],
            renames=d["renames"],
        )


@dataclass(frozen=True)
class Config:
    id: str
    base_url: str
    output_path: str
    sources: dict[str, ConfigSource]

    @classmethod
    def from_dict(cls: "Config", d: dict) -> "Config":
        return cls(
            id=d["id"],
            base_url=d["base_url"],
            output_path=d["output_path"],
            sources={k: ConfigSource.from_dict(v) for k, v in d["sources"].items()},
        )


@dataclass(frozen=True)
class DatabaseFile:
    hash: str
    size: int

    @classmethod
    def from_dict(cls: "DatabaseFile", d: dict) -> "DatabaseFile":
        return cls(
            hash=d["hash"],
            size=d["size"]
        )


@dataclass(frozen=True)
class DatabaseFolder:
    pass


@dataclass(frozen=True)
class Database:
    base_files_url: str
    db_id: str
    db_url: str
    files: dict[str, DatabaseFile]
    folders: dict[str, DatabaseFolder]
    timestamp: int

    @classmethod
    def from_dict(cls: "Database", d: dict) -> "Database":
        return cls(
            base_files_url=d["base_files_url"],
            db_id=d["db_id"],
            db_url=d["db_url"],
            files={k: DatabaseFile.from_dict(v) for k, v in d["files"].items()},
            folders={k: DatabaseFolder() for k in d["folders"].keys()},
            timestamp=d["timestamp"],
        )


@dataclass(frozen=True)
class PathListFile:
    remote_name: str
    remote_url: str
    remote_glob: str | None
    expected_size: int
    expected_hash: str
    local_name: str
    local_path: str


class PathList:
    files: dict[str, PathListFile]
    folders: set[str]
    timestamp: int

    def __init__(self):
        self.files = {}
        self.folders = set()
        self.timestamp = 0


class SourceTransformer:
    output_path: str
    pathlist: PathList

    def __init__(self, output_path: str):
        self.output_path = output_path
        self.pathlist = PathList()

    @staticmethod
    def download_remote_db(url: str) -> Database:
        with urlopen(url) as response_stream:
            zip_stream = BytesIO(response_stream.read())
            with ZipFile(zip_stream) as zip_file:
                db_file = zip_file.namelist()[0]
                with zip_file.open(db_file) as db_stream:
                    return Database.from_dict(json.load(db_stream))

    @staticmethod
    def source_files(source: ConfigSource, db: Database) -> Iterable[Tuple[str, str, str | None]]:
        # if glob has no magic characters, we can improve performance by not using fnmatch
        for remote_glob in source.entries:
            try:
                name = fnfilter(db.files.keys(), remote_glob)[0]
                yield name, name, None if remote_glob == name else remote_glob
            except IndexError:
                logger.error(f"No files matching '{remote_glob}' found in {db.db_id}")

        for local_name, remote_glob in source.renames.items():
            try:
                remote_name = fnfilter(db.files.keys(), remote_glob)[0]
                yield local_name, remote_name, None if remote_glob == remote_name else remote_glob
            except IndexError:
                logger.error(f"No files matching '{remote_glob}' found in {db.db_id}")

    def add_source(self, source: ConfigSource) -> None:
        try:
            remote_db = self.download_remote_db(source.url)
        except IOError:
            logger.error(f"Unable to download source database from '{source.url}'")
            return

        # use the most recent timestamp
        self.pathlist.timestamp = max(self.pathlist.timestamp, remote_db.timestamp)

        for local_name, remote_name, remote_glob in self.source_files(source, remote_db):
            self.pathlist.folders.add(path.dirname(remote_name))
            self.pathlist.files[local_name] = PathListFile(
                remote_name=remote_name,
                remote_url=path.join(remote_db.base_files_url, urlquote(remote_name)),
                remote_glob=remote_glob,
                expected_size=remote_db.files[remote_name].size,
                expected_hash=remote_db.files[remote_name].hash,
                local_name=local_name,
                local_path=path.join(self.output_path, local_name)
            )


class FileManager:
    config: Config
    pathlist: PathList

    def __init__(self, config: Config, pathlist: PathList):
        self.config = config
        self.pathlist = pathlist

    @staticmethod
    def is_outdated(file: PathListFile) -> bool:
        try:
            with open(file.local_path, "rb") as file_stream:
                file_content = file_stream.read()
                if len(file_content) != file.expected_size:
                    logger.info(f"File '{file.local_name}' has invalid size")
                    return True
                file_hash = md5(file_content).hexdigest()
                if file_hash != file.expected_hash:
                    logger.info(f"File '{file.local_name}' has invalid hash")
                    return True
        except FileNotFoundError:
            logger.info(f"File '{file.local_name}' not found")
            return True
        return False

    def unlink_outdated(self, entry: PathListFile) -> None:
        if entry.remote_glob:
            try:
                for outdated_path in glob(path.join(self.config.output_path, entry.remote_glob)):
                    logger.info(f"Deleting outdated file '{outdated_path}'")
                    unlink(outdated_path)
            except IOError:
                logger.warning(f"Unable to delete files matching '{entry.remote_glob}'")
        else:
            logger.debug(f"No glob pattern for {entry.local_name}, skipping deletion")

    @staticmethod
    def download_updated(entry: PathListFile) -> None:
        try:
            logger.info(f"Downloading file '{entry.local_name}'")
            with urlopen(entry.remote_url) as response_stream:
                with open(entry.local_path, "wb") as output_stream:
                    output_stream.write(response_stream.read())
        except IOError:
            logger.error(f"Unable to download file '{entry.local_name}'")

    def download_files(self) -> None:
        for entry in self.pathlist.files.values():
            if self.is_outdated(entry):
                self.unlink_outdated(entry)
                self.download_updated(entry)

    def create_folders(self) -> None:
        try:
            for folder in self.pathlist.folders:
                local_path = path.join(self.config.output_path, folder)
                makedirs(local_path, exist_ok=True)
        except IOError:
            logger.critical(f"Unable to create output folder '{self.config.output_path}'")
            sys.exit(1)


class DatabaseBuilder:
    config: Config
    pathlist: PathList

    def __init__(self, config: Config, pathlist: PathList):
        self.config = config
        self.pathlist = pathlist

    def build(self) -> Database:
        folders = {f: DatabaseFolder() for f in self.pathlist.folders}
        files = {
            f.local_name: DatabaseFile(hash=f.expected_hash, size=f.expected_size)
            for f in self.pathlist.files.values()
        }

        return Database(
            base_files_url=self.config.base_url,
            db_id=self.config.id,
            db_url=path.join(self.config.base_url, f"{self.config.id}.json.zip"),
            files=files,
            folders=folders,
            timestamp=self.pathlist.timestamp
        )

    def save(self) -> None:
        try:
            db = self.build()
            db_path = path.join(self.config.output_path, f"{self.config.id}.json.zip")
            with ZipFile(db_path, "w") as zip_file:
                db_file = f"{db.db_id}.json"
                with zip_file.open(db_file, "w") as db_stream:
                    json.dump(asdict(db), TextIOWrapper(db_stream))
        except IOError:
            logger.critical(f"Unable to save proxied database to '{self.config.output_path}'")
            sys.exit(1)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) != 2:
        print(f"Usage: {path.basename(sys.argv[0])} <config_path>", file=sys.stderr)
        sys.exit(1)

    try:
        with open(sys.argv[1]) as stream:
            config = Config.from_dict(json.load(stream))
    except IOError:
        logger.critical(f"Unable to load config file '{sys.argv[1]}'")
        sys.exit(1)

    transformer = SourceTransformer(config.output_path)
    for source in config.sources.values():
        transformer.add_source(source)

    file_manager = FileManager(config, transformer.pathlist)
    file_manager.create_folders()
    file_manager.download_files()

    db_builder = DatabaseBuilder(config, transformer.pathlist)
    db_builder.save()


if __name__ == "__main__":
    main()
