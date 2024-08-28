# mdproxy

`mdproxy` is used to generate a [MiSTer Downloader](https://github.com/MiSTer-devel/Downloader_MiSTer) custom database
file that should be served to instances of MiSTer Downloader over the web. It takes care of downloading the remote files
and supports renaming.

## Installation

Given it's just a file, you may install it to any directory of your choice with a single line:

```bash
install -m 755 mdproxy.py /some/path/mdproxy
```

However, a `Makefile` is provided for convenience, if you want to install system-wide
(defaults to `/usr/bin`):

```bash
sudo make install
```

## Usage

`mdproxy` takes a single mandatory argument, which is a configuration file:

```bash
mdproxy config.json
```

If any error occurs, it outputs to standard error the relevant message. Some errors are recoverable, and in general
`mdproxy` will do its best to keep going unless a critical error happens, in which case it will exit with a status code
of `1`.

## Configuration

The configuration file is in JSON format:

```json
{
  "id": "arcade",
  "base_url": "https://mister.example.com",
  "output_path": "dist",
  "sources": {
    "mister": {
      "url": "https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip",
      "entries": [
        "_Arcade/Ninja Baseball Bat Man (World).mra",
        "_Arcade/R-Type (World).mra",
        "_Arcade/R-Type II (World).mra",
        "_Arcade/R-Type Leo (World).mra",
        "_Arcade/cores/Arkanoid_*.rbf",
        "_Arcade/cores/IremM72_*.rbf",
        "_Arcade/cores/IremM92_*.rbf",
        "_Arcade/cores/SolomonsKey_*.rbf"
      ],
      "renames": {
        "_Arcade/Arkanoid (World).mra": "_Arcade/Arkanoid (W).mra",
        "_Arcade/Solomon's Key (World).mra": "_Arcade/Solomon's Key.mra"
      }
    }
  }
}
```

- `id` represents the custom database id. It must be unique among other databases in your MiSTer downloader
  configuration. It is also used to generate the filename of the database zip file.
- `base_url` represents the base URL from which the files will be served. For example, the URL of the database zip file
  in the sample configuration will be `https://mister.example.com/arcade.json.zip`.
- `output_path` represents a location in your filesystem where all the files will be saved, including the database zip
  file.
- `sources` represents a list of sources from which files will be imported into our custom databases.
    - `url` represents the URL of the source database zip file.
    - `entries` represents the list of files that needs to be imported as it is. Each entry can be a glob, in which case
      only the first match will be copied over.
    - `renames` represents the list of files that needs to be imported and renamed. The left hand side is the target (
      local) filename, while the right hand side is the source (remote) filename. Source filenames can be specified as a
      glob, in which case only the first match will be copied over to the specified target filename.
