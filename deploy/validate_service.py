"""Check an operator-filled systemd unit before installing or starting it.

This static check does not contact systemd, read secrets, or test filesystem
permissions, ingress, TLS, or a running host.
"""

import argparse
import shlex
import sys
from pathlib import Path
from urllib.parse import urlsplit

DATA_KEYS = ("TABLET_WALL_DB", "TABLET_WALL_ASSET_DIR", "TABLET_WALL_MEDIA_DIR")
ORIGIN_KEYS = ("TABLET_WALL_OPERATOR_ORIGIN", "TABLET_WALL_TABLET_ORIGIN")


def validate_service(text: str, *, scope: str) -> list[str]:
    """Return all static deployment errors in a filled unit."""
    errors: list[str] = []
    entries: dict[str, list[str]] = {}
    environment: dict[str, str] = {}
    section = ""
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if "REPLACE" in line or "<" in line or ">" in line:
            errors.append(f"line {number}: replace the placeholder")
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line or line.endswith("\\"):
            errors.append(f"line {number}: expected one complete key=value directive")
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        entries.setdefault(f"{section}.{key}", []).append(value)
        if section == "Service" and key == "Environment":
            try:
                for assignment in shlex.split(value):
                    name, separator, setting = assignment.partition("=")
                    if not separator:
                        raise ValueError("expected NAME=value")
                    if name in environment:
                        errors.append(f"line {number}: duplicate environment setting {name}")
                    environment[name] = setting
            except ValueError as error:
                errors.append(f"line {number}: invalid Environment: {error}")

    def single(key: str) -> str:
        values = entries.get(key, [])
        if len(values) != 1 or not values[0]:
            errors.append(f"{key}: exactly one nonempty directive is required")
            return ""
        return values[0]

    working = single("Service.WorkingDirectory")
    if working and not Path(working).is_absolute():
        errors.append("WorkingDirectory must be absolute")
    for key in DATA_KEYS:
        value = environment.get(key, "")
        if not value or not Path(value).is_absolute():
            errors.append(f"{key}: an explicit absolute path is required")
    if len({environment.get(key) for key in DATA_KEYS}) != len(DATA_KEYS):
        errors.append("database, asset and media paths must be different")
    for key in ORIGIN_KEYS:
        value = environment.get(key, "")
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme == "https" and parsed.hostname
                     and not parsed.username and not parsed.password
                     and not parsed.path and not parsed.query and not parsed.fragment)
            # Accessing port also checks malformed and out-of-range values.
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            errors.append(f"{key}: a bare HTTPS origin without a trailing slash is required")
    if environment.get(ORIGIN_KEYS[0]) == environment.get(ORIGIN_KEYS[1]):
        errors.append("tablet and operator origins must be different")
    if environment.get("TABLET_WALL_UPLOAD_MODE") not in {"disabled", "proxy"}:
        errors.append("service upload mode must be disabled or proxy")

    command = single("Service.ExecStart")
    try:
        args = shlex.split(command)
    except ValueError as error:
        errors.append(f"ExecStart: {error}")
        args = []
    if args:
        if Path(args[0]).name != "fastapi":
            errors.append("ExecStart executable must be fastapi")
        if not Path(args[0]).is_absolute():
            errors.append("ExecStart executable must be absolute")
        if args[1:3] != ["run", "main.py"]:
            errors.append("ExecStart must run main.py with fastapi run")
        if "--workers" in args or any(arg.startswith("--workers=") for arg in args):
            errors.append("ExecStart must use the default single worker")
        hosts = [args[index + 1] for index, arg in enumerate(args[:-1]) if arg == "--host"]
        hosts += [arg.split("=", 1)[1] for arg in args if arg.startswith("--host=")]
        if hosts != ["127.0.0.1"]:
            errors.append("ExecStart must explicitly bind --host 127.0.0.1 once")
    if scope == "system":
        user = single("Service.User")
        if user in {"root", "0"}:
            errors.append("system services must use a dedicated non-root User")
    elif entries.get("Service.User") or entries.get("Service.Group"):
        errors.append("user units must not set User or Group")
    wanted = single("Install.WantedBy")
    if wanted != ("multi-user.target" if scope == "system" else "default.target"):
        errors.append("Install.WantedBy does not match the selected scope")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit", type=Path)
    parser.add_argument("--scope", choices=("system", "user"), required=True)
    args = parser.parse_args(argv)
    try:
        errors = validate_service(args.unit.read_text(), scope=args.scope)
    except (OSError, UnicodeError) as error:
        print(f"cannot read unit: {error}", file=sys.stderr)
        return 2
    if errors:
        for problem in errors:
            print(problem, file=sys.stderr)
        return 1
    print("Static service checks passed; validate permissions, systemd and ingress on the host.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
