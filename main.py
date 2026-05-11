from collections.abc import Iterator
import json
import os
import shutil
import subprocess
import pathlib
import zipfile

import pydantic
import yaml

type _Config = dict[str, str | _Config]


def main() -> None:
    minijinja_cli = shutil.which('minijinja-cli.exe')
    if not minijinja_cli:
        raise FileNotFoundError('minijinja-cli.exe')

    root = pathlib.Path(os.environ['PIXI_PROJECT_ROOT'])
    resources = root / 'resources'
    script = _powershell(minijinja_cli, resources)

    with zipfile.ZipFile(
        root / 'post-init.zip',
        'w',
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=False,
        compresslevel=9,
    ) as f:
        f.writestr('post-init.ps1', script)
        f.write(minijinja_cli, 'resources/minijinja-cli.exe')
        for name in 'post-init.reg.jinja', 'secedit.inf':
            f.write(resources / name, 'resources/' + name)


def _links(cfg: object) -> Iterator[tuple[str, str]]:
    adapter = pydantic.TypeAdapter[_Config](_Config)
    for k, v in adapter.validate_python(cfg).items():
        if isinstance(v, str):
            yield k, v
        else:
            for k2, v2 in _links(v):
                yield os.path.join(k, k2), v2


def _powershell(
    minijinja_cli: str,
    resources: pathlib.Path,
) -> bytes:
    with (resources / 'links.yml').open(encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    mkdir = {r"'D:\Public'"}
    new_item: list[dict[str, str]] = []
    for k, v in _links(cfg):
        v = os.path.abspath(v)

        if os.path.isdir(v):
            item_type = 'Junction'
        elif os.path.isfile(v) or input(
            f"{v} doesn't exist. Is it supposed to be a directory? (Y/n) ",
        ).lstrip().startswith(('n', 'N')):
            item_type = 'SymbolicLink'
        else:
            item_type = 'Junction'

        if k.startswith('$'):
            d = os.path.dirname(k)
            k = f'"$Env:{k[1:]}"'
            if d:
                mkdir.add(f'"$Env:{d[1:]}"')
            else:
                mkdir.add(f'(Split-Path {k})')
        else:
            mkdir.add(f"'{os.path.dirname(k)}'")
            k = f"'{k}'"

        if item_type == 'Junction':
            v = f"'{v}'"
            mkdir.add(v)
        else:
            mkdir.add(f"'{os.path.dirname(v)}'")
            v = f"'{v}'"

        new_item.append({'ItemType': item_type, 'Path': k, 'Value': v})

    return subprocess.check_output(
        [
            minijinja_cli,
            '-f', 'json',
            resources / 'post-init.ps1.jinja',
            '-',
        ],
        input=json.dumps({
            'mkdir': sorted(mkdir),
            'new_item': new_item,
        }).encode(),
    )


if __name__ == '__main__':
    main()
