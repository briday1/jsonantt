"""Read-only Git history, scoped to the file explicitly opened by the server."""
from pathlib import Path
import subprocess


def _git(directory, *args):
    try:
        return subprocess.check_output(['git', '--literal-pathspecs', '-C', str(directory), *args],
                                       stderr=subprocess.PIPE, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Git history is unavailable: open a tracked JSON file in a Git repository.') from exc


def file_history(path):
    path = Path(path).resolve()
    root = Path(_git(path.parent, 'rev-parse', '--show-toplevel').decode().strip())
    relative = path.relative_to(root).as_posix()
    raw = _git(root, 'log', '-200', '--follow', '--format=%H%x00%cI%x00%s', '--name-only', '-z', '--', relative)
    parts = raw.decode('utf-8', errors='replace').split('\0')
    entries = []
    for offset in range(0, len(parts) - 3, 4):
        sha, timestamp, message, filename = parts[offset:offset + 4]
        entries.append({'sha': sha, 'date': timestamp, 'message': message, 'path': filename[1:] if filename.startswith('\n') else filename})
    return root, entries


def revision_source(path, sha):
    root, entries = file_history(path)
    entry = next((entry for entry in entries if entry['sha'] == sha), None)
    if entry is None:
        raise ValueError('Choose a revision from this file\'s history (latest 200 commits).')
    return _git(root, 'show', f"{entry['sha']}:{entry['path']}").decode('utf-8')
