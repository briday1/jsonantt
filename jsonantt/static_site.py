"""Build the static studio with the current Python sources, never a fork."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED


def build_site(output, prerender=False):
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
    digest = hashlib.sha256()
    for source in sorted(package.glob('*.py')) + sorted((package / 'web').glob('*.mjs')):
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    version = digest.hexdigest()
    index = output / 'index.html'
    index.write_text(index.read_text().replace('name="jsonantt-static-build" content=""',
                                             f'name="jsonantt-static-build" content="{version}"'))
    previews = []
    if prerender:
        # JavaScript remains the one source of demo data; Python remains the
        # one drawing implementation. These are interactive SVGs, not images.
        command = f'import {{DEMOS}} from {json.dumps((package / "web/demo-charts.mjs").as_uri())}; console.log(JSON.stringify(DEMOS));'
        demos = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', command], text=True))
        from jsonantt.parser import parse_chart
        from jsonantt.renderer import render_chart
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preview.svg'
            for doc in demos.values():
                if doc.get('style', {}).get('today_marker'):
                    continue
                render_chart(parse_chart(doc), str(path), interactive=True)
                previews.append({'source': json.dumps(doc, ensure_ascii=False, separators=(',', ':')),
                                 'options': {'mode':'gantt', 'renderDepth':doc.get('style', {}).get('render_depth', 0)},
                                 'svg': path.read_text()})
    (output / 'startup-previews.json').write_text(json.dumps({'version':version, 'previews':previews}, ensure_ascii=False))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='_site')
    parser.add_argument('--prerender', action='store_true', help='Generate instant demo previews with the Python renderer (requires Node.js)')
    args = parser.parse_args()
    print(build_site(args.output, prerender=args.prerender))
