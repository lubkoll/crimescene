import re

######################################################################
## Complexity calcualations
######################################################################

leading_tabs_expr = re.compile(r'^(\t+)')
leading_spaces_expr = re.compile(r'^( +)')
empty_line_expr = re.compile(r'^\s*$')
comment_line_expr = re.compile(r'^\s*(//+|\*+/|/\*+).*$')


def n_log_tabs(line):
    pattern = re.compile(r' +')
    wo_spaces = re.sub(pattern, '', line)
    m = leading_tabs_expr.search(wo_spaces)
    if m:
        tabs = m.group()
        return len(tabs)
    return 0


def n_log_spaces(line):
    pattern = re.compile(r'\t+')
    wo_tabs = re.sub(pattern, '', line)
    m = leading_spaces_expr.search(wo_tabs)
    if m:
        spaces = m.group()
        return len(spaces)
    return 0


def contains_code(line):
    return not (empty_line_expr.match(line) or comment_line_expr.match(line))


OFFSET = 4


def complexity_of(line, previous_line_complexity):
    n_spaces = n_log_spaces(line)
    complexity = n_log_tabs(line) + (n_spaces / OFFSET
                                     )  # hardcoded indentation
    if n_spaces % OFFSET == 0 or complexity < previous_line_complexity:
        return complexity
    return previous_line_complexity


######################################################################
## Statistics from complexity
######################################################################


def compute_lines(source):
    return sum(1 for line in source.split('\n') if contains_code(line))


def calculate_complexity_in(source):
    #    source = re.sub(r'/\*.*\*/', '', source)
    complexity = []
    counter = -1
    for line in source.split("\n"):
        if contains_code(line):
            previous_line_complexity = 0 if not complexity else complexity[
                counter]
            complexity.append(complexity_of(line, previous_line_complexity))
            counter += 1

    return complexity
    # return [
    #     complexity_of(line) for line in source.split("\n")
    #     if contains_code(line)
    # ]
