from datetime import datetime, timezone
import json
from typing import List
from git_data import Commit, Change, add_parents_and_children


# sha: str = ''
# parent_shas: list = field(default_factory=list)
# child_shas: list = field(default_factory=list)
# parents: Iterable = field(default_factory=list)
# children: Iterable = field(default_factory=list)
# creation_time: datetime = datetime(year=2015,
#                                    month=1,
#                                    day=1,
#                                    tzinfo=timezone.utc)
# author: str = ''
# msg: str = ''
# changes: Iterable[Change] = field(default_factory=list)
# old_filename: str = ''
# filename: str = ''
# added_lines: int = 0
# removed_lines: int = 0
def store_commits(commits: List[Commit]):
    with open('commits.json', 'w') as commits_file:
        json_repr = [{
            'sha': commit.sha,
            'parent_shas': commit.parent_shas,
            'child_shas': commit.child_shas,
            'creation_time': commit.creation_time.timestamp(),
            'author': commit.author,
            'msg': commit.msg,
            'changes': [change.__dict__ for change in commit.changes]
        } for commit in commits]
        commits_file.write(json.dumps(json_repr))


def load_commits():
    with open('commits.json', 'r') as commits_file:
        json_repr = json.loads(commits_file.read())
        commits = [
            Commit(sha=entry['sha'],
                   parent_shas=entry['parent_shas'],
                   child_shas=entry['child_shas'],
                   parents=[],
                   children=[],
                   creation_time=datetime.fromtimestamp(float(
                       entry['creation_time']),
                                                        tz=timezone.utc),
                   author=entry['author'],
                   msg=entry['msg'],
                   changes=[
                       Change(old_filename=change_entry['old_filename'],
                              filename=change_entry['filename'],
                              added_lines=int(change_entry['added_lines']),
                              removed_lines=int(change_entry['removed_lines']))
                       for change_entry in entry['changes']
                   ]) for entry in json_repr
        ]

        add_parents_and_children(commits)
        return commits


def store_stats(stats):
    with open('stats.json', 'w') as stats_file:
        stats_file.write(json.dumps(stats))


def load_stats():
    with open('stats.json', 'r') as stats_file:
        return json.loads(stats_file.read())
