from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Iterable, List, Tuple


@dataclass
class Change:
    old_filename: str = ''
    filename: str = ''
    added_lines: int = 0
    removed_lines: int = 0
    removed: bool = False

    def __str__(self) -> str:
        return f'Change(old_filename={self.old_filename}, filename={self.filename}, added_lines={self.added_lines}, removed_lines={self.removed_lines})'


@dataclass
class Commit:
    sha: str = ''
    parent_shas: list = field(default_factory=list)
    child_shas: list = field(default_factory=list)
    parents: Iterable = field(default_factory=list)
    children: Iterable = field(default_factory=list)
    creation_time: datetime = datetime(year=2015,
                                       month=1,
                                       day=1,
                                       tzinfo=timezone.utc)
    author: str = ''
    msg: str = ''
    changes: Iterable[Change] = field(default_factory=list)


def get_commit(line: str) -> Commit:
    commit_match = re.match(
        r"'*\[(\w+)\]\s+\[(.*)\]\s+(\w.*\w)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+[\+\-]*\d{4})\s+(\S.*)",
        #        r"'\[(\w+)\]\s+(\w.*\w)\s+(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+\+(\d{4})\s+(\S.*)",
        line)
    if not commit_match:
        print(f'Failed to match commit in: {line}')
        return None

    creation_time = datetime.strptime(commit_match.group(4),
                                      '%Y-%m-%d %H:%M:%S %z')
    return Commit(sha=commit_match.group(1),
                  parent_shas=commit_match.group(2).split(' '),
                  author=commit_match.group(3),
                  creation_time=creation_time,
                  msg=commit_match.group(5).replace("'", ""))


def get_change(line: str) -> Change:
    change_match = re.match(r'([0-9]+)\s+([0-9]+)\s+(\S+.*)', line)
    if change_match:
        old_name = ''
        name = change_match.group(3)

        if '=>' in name:
            mapping_regex = r'.*(\{\S*\s*=>\s*\S*\})(.*)' if '{' in name else r'(\S*\s*=>\s*\S*)'
            mapping_match = re.match(mapping_regex, name)
            if mapping_match:
                mapping = mapping_match.group(1)
                rename_regex = r'\{(\S*)\s*=>\s*(\S*)\}' if '{' in name else r'(\S*)\s*=>\s*(\S*)'
                rename_match = re.match(rename_regex, mapping)
                # case: new folder introduced
                if rename_match.group(1):
                    old_name = name.replace(mapping, rename_match.group(1))
                else:
                    old_name = name.replace('/' + mapping, '')
                if rename_match.group(2):
                    name = name.replace(mapping, rename_match.group(2))
                else:
                    name = name.replace('/' + mapping, '')
        return Change(old_filename=old_name,
                      filename=name,
                      added_lines=int(change_match.group(1)),
                      removed_lines=int(change_match.group(2)))


def add_parents_and_children(commits: List[Commit]):
    for commit in commits:
        for parent_sha in commit.parent_shas:
            for parent in commits:
                if parent.sha == parent_sha:
                    parent.children.append(commit)
                    parent.child_shas.append(commit.sha)
                    commit.parents.append(parent)


def get_commit_list(git_log: str) -> Tuple[Commit]:
    lines = git_log.split('\n')
    commits = []
    current_commit = None
    for line in lines:
        if not line:
            continue
        if line.startswith("'[") or line.startswith("["):
            if current_commit:
                commits.append(current_commit)
                current_commit = None
            current_commit = get_commit(line)
            continue

        if current_commit and re.match(r'[0-9]+.*', line):
            change = get_change(line)
            if change:
                current_commit.changes.append(change)
            continue
        match = re.match(r'\s*(delete)\s+mode\s+\d{6}\s+(\S+.*)', line)
        if match:
            filename = match.group(2)
            for change in current_commit.changes:
                if change.filename == filename:
                    change.removed = True
                    break

    if current_commit:
        commits.append(current_commit)

    add_parents_and_children(commits)

    return list(sorted(commits, key=lambda commit: commit.creation_time))