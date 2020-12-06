import argparse
import csv
import time
import os
from collections import OrderedDict
from datetime import datetime, timedelta

from git_log import DescriptiveStats
import miner.complexity_calculations as complexity_calculations

DATE_FORMAT = '%Y-%m-%d'


def to_days(delta: timedelta):
    return delta / timedelta(days=1)


def to_ms(delta: timedelta):
    return delta / timedelta(milliseconds=1)


def get_name(base: str,
             end: datetime,
             period_length: timedelta,
             suffix: str = 'csv'):
    return f'{base}_{end.strftime(DATE_FORMAT)}_{to_days(period_length)}.{suffix}'


def parse(filename: str, parse_action):
    with open(filename, 'r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            parse_action(row)


def add_complexity_analysis(root: str, end: str, stats):
    os.system(
        f'cd {root} && git checkout `git rev-list -n 1 --before={end} master`')
    try:
        for filename in stats.keys():
            with open(root + filename, "r") as file_to_calc:
                complexity_by_line = complexity_calculations.calculate_complexity_in(
                    file_to_calc.read())
                d_stats = DescriptiveStats(filename, complexity_by_line)
                if not stats[filename]:
                    print(f'MISSING: {filename}')
                stats[filename]['lines'] = d_stats.n_revs
                stats[filename]['complexity'] = d_stats.total
                stats[filename]['mean_complexity'] = round(d_stats.mean(), 2)
                stats[filename]['complexity_sd'] = round(d_stats.sd(), 2)
                stats[filename]['complexity_max'] = round(
                    d_stats.max_value(), 2)
    except Exception as exc:
        print(f'Exc: {type(exc)}:{exc}')
    os.system(f'cd {root} && git checkout master')
    return stats


def merge(root: str, rev_file: str, loc_file: str, soc_file: str, end: str):
    loc_stats = {}

    def store_loc(row):
        loc_stats[row['filename'][2:]] = OrderedDict(loc=int(row['code']))

    parse(filename=loc_file, parse_action=store_loc)
    nrev_stats = {}

    def store_nrevs(row):
        if 'entity' in row:
            nrev_stats[row['entity']] = OrderedDict(
                revisions=int(row['n-revs']))

    parse(filename=rev_file, parse_action=store_nrevs)

    stats = {
        key: {
            'soc': 0.0,
            **value,
            **nrev_stats[key]
        }
        for key, value in loc_stats.items() if key in nrev_stats.keys()
    }

    def store_soc(row):
        if not 'entity' in row:
            return
        name = row['entity']
        if name in stats:
            stats[name]['soc'] = int(row['soc'])

    parse(filename=soc_file, parse_action=store_soc)
    return add_complexity_analysis(root=root, end=end, stats=stats)


def get_summary(root: str, stats_path: str, end: datetime, period: timedelta):
    summary = 'Summary:</br>'
    initial_commit_date = ''
    initial_commit_sha = ''
    last_commit_sha = ''
    git_log = get_name(base='git', end=end, period_length=period, suffix='log')
    summary_csv = get_name(base='summary', end=end, period_length=period)
    summary_path = f'{stats_path}/{summary_csv}'

    if not os.path.exists(summary_path):
        os.system(
            f'cd {root} && docker run -v {stats_path}:/data --rm code-maat maat -l /data/{git_log} -c git -a summary > {summary_path}'
        )
    with open(summary_path, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        first_line = True
        for line in csv_reader:
            if first_line:
                first_line = False
                continue
            summary += line['statistic'].replace('number-of-', '#').replace(
                'entities-changed', 'changed') + ': ' + line['value'] + '</br>'
    with open(f'{stats_path}/initial_commit_date.txt',
              mode='r') as initial_commit_file:
        for line in initial_commit_file:
            summary += f'First commit: {line}'
            initial_commit_date = datetime.strptime(line, DATE_FORMAT)
            break

    with open(f'{stats_path}/initial_commit_sha.txt',
              mode='r') as initial_commit_file:
        for line in initial_commit_file:
            initial_commit_sha = line[:-1]
            break
    with open(f'{stats_path}/last_commit_sha.txt',
              mode='r') as last_commit_file:
        for line in last_commit_file:
            last_commit_sha = line[:-1]
            break
    return summary, initial_commit_date, initial_commit_sha, last_commit_sha


def write_meta(root: str, start: datetime, end: datetime,
               period_length: timedelta, stats_path: str):
    start_str = start.strftime(DATE_FORMAT)
    end_str = end.strftime(DATE_FORMAT)
    git_log = get_name(base='git',
                       end=end,
                       period_length=period_length,
                       suffix='log')
    revisions_csv = get_name(base='revisions',
                             end=end,
                             period_length=period_length)
    loc_csv = get_name(base='loc', end=end, period_length=period_length)
    soc_csv = get_name(base='soc', end=end, period_length=period_length)
    git_log_path = f'{stats_path}/{git_log}'
    revisions_path = f'{stats_path}/{revisions_csv}'
    loc_path = f'{stats_path}/{loc_csv}'
    soc_path = f'{stats_path}/{soc_csv}'
    print(f' === Analyzing git history from {start} to {end}.')
    start_time = time.time()
    os.system(f'mkdir -p {stats_path}')
    if not os.path.exists(f'{stats_path}/initial_commit_date.txt'):
        os.system(
            f'cd {root} && git log --pretty=format:"%ad" --date=short | tail -1 > {stats_path}/initial_commit_date.txt'
        )
    if not os.path.exists(f'{stats_path}/last_commit_sha.txt'):
        os.system(
            f'cd {root} && git rev-list HEAD | tail -n 1 > {stats_path}/last_commit_sha.txt'
        )
    os.system(
        f'cd {root} && git rev-parse HEAD > {stats_path}/last_commit_sha.txt')
    os.system(
        f'cd {root} && git checkout `git rev-list -n 1 --before={end_str} master`'
    )
    if not os.path.exists(git_log_path):
        os.system(
            f'cd {root} && git log --pretty=format:"[%h] %an %ad %s" --date=short --after={start_str} --before={end_str} --numstat > {git_log_path}'
        )
    rename_regex = '"s@\(.*\){\(.*\) => \(.*\)}@\\1\\3@g"'
    os.system(f'cd {root} && sed -i {rename_regex} {git_log_path}')
    if not os.path.exists(revisions_path):
        os.system(
            f'cd {root} && docker run -v {stats_path}:/data --rm code-maat maat -l /data/{git_log} -c git -a revisions > {revisions_path}'
        )
    if not os.path.exists(loc_path):
        os.system(
            f'cd {root} && cloc ./ --unix --by-file --csv --quiet --exclude-dir=build,build-Release,.cmake --report-file={loc_path}'
        )
        # valid_names = []
        # with open(revisions_path, 'r') as csv_file:
        #     reader = csv.DictReader(csv_file)
        #     for line in reader:
        #         valid_names.append(line['entity'])

        # print(f'valid {valid_names}')
        # with open(loc_path, 'r') as csv_file:
        #     reader = csv.DictReader(csv_file)
        #     for line in reader:
        #         name = line['filename'][2:]
        #         if name not in valid_names:
        #             print(f'name: {name}')
        #             cmd = f'sed -i "\:{name}:d" {loc_path}'
        #             print(f'CMD: {cmd}')
        #             os.system(f'sed -i "/{name}/d" {loc_path}')
    if not os.path.exists(soc_path):
        os.system(
            f'cd {root} && docker run -v {stats_path}:/data --rm code-maat maat -l /data/{git_log} -c git -a soc > {soc_path}'
        )
    os.system(f'cd {root} && git checkout master')
    end_time = time.time()
    print(
        f' === Analysis finished after {round(end_time - start_time, 2)} seconds.'
    )


def write_all_meta(root: str, start: datetime, end: datetime,
                   period_length: timedelta, stats_path: str):
    period_step = timedelta(days=1)
    n_stats = int((end - start) / period_step) + 1
    ranges = [(end - period_length - i * period_step, end - i * period_step)
              for i in range(n_stats)]
    for r in ranges:
        write_meta(root=root,
                   start=r[0],
                   end=r[1],
                   period_length=period_length,
                   stats_path=stats_path)


def analyze_git_history(root: str, start: datetime, end: datetime,
                        period_length: timedelta, stats_path: str):
    #    write_meta(root=root, start=start, end=end, period_length=period_length, stats_path=stats_path)
    revisions_csv = get_name(base='revisions',
                             end=end,
                             period_length=period_length)
    loc_csv = get_name(base='loc', end=end, period_length=period_length)
    soc_csv = get_name(base='soc', end=end, period_length=period_length)
    revisions_path = f'{stats_path}/{revisions_csv}'
    loc_path = f'{stats_path}/{loc_csv}'
    soc_path = f'{stats_path}/{soc_csv}'
    print(f'PATHS {revisions_path} {loc_path} {soc_path}')
    return merge(root=root,
                 rev_file=revisions_path,
                 loc_file=loc_path,
                 soc_file=soc_path,
                 end=end.strftime(DATE_FORMAT))


def analyze_git_histories(root: str, start: datetime, end: datetime,
                          period_step: timedelta, period: timedelta,
                          stats_path: str):
    n_stats = int((end - start) / period_step) + 1
    ranges = [(end - period - i * period_step, end - i * period_step)
              for i in range(n_stats)]
    start_time = time.time()
    stats = {
        range[1]: analyze_git_history(root=root,
                                      start=range[0],
                                      end=range[1],
                                      period_length=period,
                                      stats_path=stats_path)
        for range in ranges
    }
    summary, initial_commit_date, initial_commit_sha, last_commit_sha = get_summary(
        root=root, stats_path=stats_path, end=end, period=period)
    print(
        f' === Overall analysis finished after {(time.time() - start_time)/60} minutes.'
    )
    return stats, summary, initial_commit_date, initial_commit_sha, last_commit_sha


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze a git log')
    parser.add_argument('--root',
                        type=str,
                        required=True,
                        help='Repository root directory')
    parser.add_argument('--start',
                        type=str,
                        required=True,
                        help='Start date YYYY-MM-DD')
    parser.add_argument('--end',
                        type=str,
                        required=True,
                        help='End date YYYY-MM-DD')
    parser.add_argument('--period-length',
                        type=int,
                        required=True,
                        help='Observation period length in days')
    parser.add_argument('--stats_path',
                        type=str,
                        required=True,
                        help='Output path for analysis results')

    args = parser.parse_args()
    write_all_meta(root=args.root,
                   start=datetime.strptime(args.start, DATE_FORMAT),
                   end=datetime.strptime(args.end, DATE_FORMAT),
                   period_length=timedelta(days=args.period_length),
                   stats_path=args.stats_path)
