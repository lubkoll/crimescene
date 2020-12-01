######################################################################
## This program calulcates the whitespace complexity of a file.
######################################################################

#!/bin/env python
import csv
import argparse
import desc_stats
import complexity_calculations
    
######################################################################
## Statistics from complexity
######################################################################

def as_stats(revision, complexity_by_line):
    return desc_stats.DescriptiveStats(revision, complexity_by_line)
    
######################################################################
## Output
######################################################################

def as_csv(f, stats):
    fields_of_interest = [f, stats.n_revs, stats.total, round(stats.mean(),2), round(stats.sd(),2), stats.max_value()]
    printable = [str(field) for field in fields_of_interest]
    return ','.join(printable)

######################################################################
## Main
######################################################################

def read_files_from_csv(filename):
    files = []
    with open(filename, 'r') as csv_file:
        reader = csv.DictReader(csv_file)
        first_line = True
        for line in reader:
            if first_line:
                first_line = False
                continue
            files.append(line['module'])
    return files
            

def run(args):
    files = read_files_from_csv(args.csv) if args.csv else args.file.split(',')
#	print 'module,n,total,mean,sd,max'
    for f in files:
        with open (f, "r") as file_to_calc:
            complexity_by_line = complexity_calculations.calculate_complexity_in(file_to_calc.read())
            stats = desc_stats.DescriptiveStats(f, complexity_by_line)
            as_csv(f, stats)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Calculates whitespace complexity of the given file.')
    parser.add_argument('--file', type=str, help='The file(s) to calculate complexity on', default="")
    parser.add_argument('--csv', type=str, help='A csv file to read the modules from', default="")
    args = parser.parse_args()
    run(args)
