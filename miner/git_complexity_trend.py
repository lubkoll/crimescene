######################################################################
## This program calulcates the complexity trend over a range of
## revisions in a Git repo.
######################################################################

#!/bin/env python
import argparse
import miner.git_interactions as git_interactions
import miner.desc_stats as desc_stats
import miner.complexity_calculations as complexity_calculations

######################################################################
## Statistics from complexity
######################################################################


def as_stats(revision, complexity_by_line):
    return desc_stats.DescriptiveStats(revision, complexity_by_line)


######################################################################
## Output
######################################################################

#def as_csv(result):
#    print 'rev,n,total,mean,sd'
#    for stats in result:
#        fields_of_interest = [stats.name, stats.n_revs, stats.total, round(stats.mean(),2), round(stats.sd(),2)]
#        printable = [str(field) for field in fields_of_interest]
#        print ','.join(printable)

######################################################################
## Main
######################################################################


def calculate_complexity_over_range(root: str, file_name, revision_range):
    start_rev, end_rev = revision_range
    revs = git_interactions.read_revs_for(root, file_name, start_rev, end_rev)
    complexity_by_rev = []
    for rev in revs:
        historic_version = git_interactions.read_version_matching(
            root, file_name, rev[0])
        complexity_by_line = complexity_calculations.calculate_complexity_in(
            historic_version)
        complexity_by_rev.append(
            (as_stats(rev[0], complexity_by_line), rev[1], rev[2]))
    return complexity_by_rev


def compute_complexity_trend(root: str, src_file: str, range):
    complexity_trend = calculate_complexity_over_range(root, src_file, range)
    return [[
        stats.name, stats.n_revs, stats.total,
        round(stats.mean(), 2),
        round(stats.sd(), 2), date, msg
    ] for stats, date, msg in complexity_trend]


def run(args):
    revision_range = args.start, args.end
    return compute_complexity_trend(src_file=args.file, range=revision_range)
    #as_csv(complexity_trend)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=
        'Calculates whitespace complexity trends over a range of revisions.')
    parser.add_argument('--start',
                        required=True,
                        help='The first commit hash to include')
    parser.add_argument('--end',
                        required=True,
                        help='The last commit hash to include')
    parser.add_argument('--file',
                        required=True,
                        type=str,
                        help='The file to calculate complexity on')

    args = parser.parse_args()
    run(args)
