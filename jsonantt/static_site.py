"""Build the static studio with the current Python sources, never a fork."""
import argparse
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED


def build_site(output):
    package = Path(__file__).resolve().parent
    output = Path(output).resolve()
    if output == package or package in output.parents or output in package.parents:
        raise ValueError('Build into a separate output directory, not the source tree')
    output.mkdir(parents=True, exist_ok=True)
    for asset in (package / 'web').iterdir():
        if asset.is_file():
            shutil.copy2(asset, output / asset.name)
    (output / 'python').mkdir(exist_ok=True)
    with ZipFile(output / 'python' / 'jsonantt.zip', 'w', ZIP_DEFLATED) as archive:
        for source in sorted(package.glob('*.py')):
            archive.write(source, f'jsonantt/{source.name}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='_site')
    print(build_site(parser.parse_args().output))
