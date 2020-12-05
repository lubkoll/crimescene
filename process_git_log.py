from time import timezone
from analyze_git_log import DATE_FORMAT
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, tzinfo
import time
import re
import subprocess


def _as_rev_range(start, end):
    return start + '..' + end


def _run_cmd(root, args):
    return subprocess.Popen(args, stdout=subprocess.PIPE,
                            cwd=root).communicate()[0].decode("utf-8")


def get_log(root: str, after: str, before: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'[%h] %an %cd %s'", '--date=short',
        f'--after={after}', f'--before={before}', '--numstat'
    ])


def get_loc(root: str, before: str):
    before_sha = _run_cmd(
        root,
        ['git', 'rev-list', '-n 1', f'--before={before}', 'master']).replace(
            '\n', '')
    _run_cmd(root, ['git', 'checkout', before_sha])
    loc = _run_cmd(root, [
        'cloc', './', '--unix', '--by-file', '--csv', '--quiet',
        '--exclude-dir=build,build-Release'
    ])
    _run_cmd(root, ['git', 'checkout', 'master'])
    return loc


def get_authors(root: str, filename: str):
    authors = defaultdict(int)
    author_summary = _run_cmd(
        root, ['git', 'shortlog', '-s', '-n', '--', filename]).split('\n')
    for line in author_summary:
        if line:
            match = re.match(r'\s+(\d+)\s+(\w.*\w)', line)
            authors[match.group(2)] = int(match.group(1))
    return authors


def get_main_authors(root: str, filename: str, max_authors: int = 3):
    authors = get_authors(root=root, filename=filename)
    valid = sorted(authors.values(), reverse=True)
    n_authors = len(valid)
    if len(valid) > max_authors:
        valid = valid[:max_authors]
    to_remove = [author for author in authors if authors[author] not in valid]
    for author in to_remove:
        authors.pop(author)
    return authors, n_authors


def get_summary(git_log: str) -> int:
    authors = set()
    n_revisions = 0
    lines = git_log.split('\n')
    for line in lines:
        if not line.startswith("'["):
            continue
        n_revisions += 1
        match = re.match(r"'\[\w+\]\s+(\w.*\w)\s+\d{4}-\d{2}-\d{2}.*", line)
        authors.add(match.group(1))
    return {'#authors': len(authors), '#revisions': n_revisions}


def read_locs(locs_str):
    lines = locs_str.split('\n')
    locs = {}
    for line in lines:
        if not line:
            continue

        entries = line.split(',')
        name = entries[1]
        if name == 'filename':
            continue
        name = name[2:]
        locs[name] = int(entries[4])
    return locs


def add_loc(revisions, locs_str):
    locs = read_locs(locs_str=locs_str)
    for name, loc in locs.items():
        revisions[name]['loc'] = loc

    to_remove = [name for name, data in revisions.items() if 'loc' not in data]
    for name in to_remove:
        del revisions[name]


def read_commit_messages(root, start: str, end: str):
    return _run_cmd(root, [
        'git', 'log', "--pretty=format:'%s'", f'--after={start}',
        f'--before={end}'
    ]).replace('\n', ' ').replace("'", "")


if __name__ == "__main__":
    start = time.time()
    root = '/home/lars/projects/Spacy'
    git_log = get_log(root=root, after='2018-09-01', before='2019-01-01')
    get_authors(root=root, filename='CMakeLists.txt')
