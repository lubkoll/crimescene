import os


class StructuralElement(object):
    def __init__(self, name, complexity):
        self.name = name
        self.complexity = complexity

    def parts(self):
        res = [x for x in self.pathParts()]
        res.reverse()
        return res

    def pathParts(self):
        (hd, tl) = os.path.split(self.name)
        while tl != '':
            yield tl
            (hd, tl) = os.path.split(hd)


def module_weight_calculator_from(analysis_results):
    max_raw_weight = max(analysis_results, key=lambda e: e[1])
    max_value = max_raw_weight[1]
    normalized_weights = dict([(name, (1.0 / max_value) * n)
                               for name, n in analysis_results])

    def normalized_weight_for(module_name):
        if module_name in normalized_weights:
            return normalized_weights[module_name]
        return 0.0

    return normalized_weight_for


######################################################################
## Building the structure of the system
######################################################################


def _matching_part_in(hierarchy, part):
    return next((x for x in hierarchy if x['name'] == part), None)


def _ensure_branch_exists(hierarchy, branch):
    existing = _matching_part_in(hierarchy, branch)
    if not existing:
        new_branch = {'name': branch, 'children': []}
        hierarchy.append(new_branch)
        existing = new_branch
    return existing


def _add_leaf(hierarchy, module, weight_calculator, name):
    # TODO: augment with weight here!
    new_leaf = {
        'name': name,
        'children': [],
        'size': module.complexity,
        'weight': weight_calculator(module.name)
    }
    hierarchy.append(new_leaf)
    return hierarchy


def _insert_parts_into(hierarchy, module, weight_calculator, parts):
    """ Recursively traverse the hierarchy and insert the individual parts 
        of the module, one by one.
        The parts specify branches. If any branch is missing, it's
        created during the traversal. 
        The final part specifies a module name (sans its path, of course).
        This is where we add size and weight to the leaf.
    """
    if len(parts) == 1:
        return _add_leaf(hierarchy, module, weight_calculator, name=parts[0])
    next_branch = parts[0]
    existing_branch = _ensure_branch_exists(hierarchy, next_branch)
    return _insert_parts_into(existing_branch['children'],
                              module,
                              weight_calculator,
                              parts=parts[1:])


def generate_structure_from(modules, weight_calculator):
    hierarchy = []
    for module in modules:
        parts = module.parts()
        _insert_parts_into(hierarchy, module, weight_calculator, parts)

    structure = {'name': 'root', 'children': hierarchy}
    return structure


def run(stats):
    raw_weights = [(name, data['revisions']) for name, data in stats.items()]
    weight_calculator = module_weight_calculator_from(raw_weights)
    structure_input = [
        StructuralElement(name, data['loc']) for name, data in stats.items()
    ]
    return generate_structure_from(structure_input, weight_calculator)
