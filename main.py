from long_term_plot import LongTermPlot
from desc_stats import as_stats
import json
import re

from stats_cache import load_commits, load_stats
from get_wordcloud import get_new_workcloud_plot
from git_log import GitLog
from file_analysis import FileAnalysis
from util import ms_to_datetime, timer, to_days
import math
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from datetime import datetime, timedelta, timezone

from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Select, Div, DateRangeSlider, Button
from bokeh.plotting import curdoc, figure
from pathlib import Path

import transform.csv_as_enclosure_json as csv_as_enclosure_json
from circular_package import CircularPackage
from color_map import get_colors

HOME = str(Path.home())
CONTROL_WIDTH = 420
PLOT_WIDTH = 1200
PLOT_HEIGHT = 900
WORDCLOUD_IDX = 2
COLUMNS = [
    'revisions', 'loc', 'complexity', 'mean_complexity', 'complexity_max',
    'complexity_sd', 'soc', 'churn', 'churn/line', 'age', 'proximity',
    'mean_proximity', 'proximity_sd', 'proximity_max'
]
CIRC_PACK_CRITERIA = [
    'soc', 'mean_complexity', 'complexity', 'complexity_sd', 'revisions',
    'author', 'age', 'churn', 'churn/line'
]
LONG_TERM_PLOT_CRITERIA = [
    'revisions', 'lines', 'complexity', 'mean complexity', 'complexity sd'
]
LEVELS = ['file', 'module']


def get_module_map(config):
    def module_map(name: str):
        for module, module_regex in config["modules"].items():
            match = re.match(module_regex, name)
            if match:
                return module
        return f'Project {config["project"]}'

    return module_map


def get_age(stats, inverse=False):
    def f(value):
        return 1 / value if inverse else value

    return {
        name:
        f(to_days(datetime.now(tz=timezone.utc) - stats[name]['last_change']))
        for name in stats
    }


@timer
def add_stats_for_module(module_stats, file_stats, module_map):
    for filename, data in file_stats.items():
        module = module_map(filename)
        module_stats[module]['loc'] += data['loc']
        module_stats[module]['lines'] += data['lines']
        module_stats[module]['complexity'] += data['complexity']
        module_stats[module]['complexity_max'] = max(
            module_stats[module]['complexity_max'], data['complexity'])
        module_stats[module]['proximity'] += data['proximity']
        module_stats[module]['proximity_max'] = max(
            module_stats[module]['proximity_max'], data['proximity'])
    for data in module_stats.values():
        data['mean_complexity'] = data['complexity'] / data['lines']
        data['mean_proximity'] = data['proximity'] / data['revisions']


@timer
def get_current_stats(full_stats, git_log: GitLog, begin: datetime,
                      end: datetime):
    stats = git_log.get_revisions_only(begin=begin, end=end)
    files = git_log.get_files_in_repository()
    to_remove = [key for key in stats if key not in files]
    for key in to_remove:
        del stats[key]
    for filename in files:
        data = full_stats.get(filename)
        if not data:
            continue
        shas_with_time = tuple(
            (sha, git_log.get_time_from_sha(sha)) for sha in data.keys())
        shas_with_time = tuple(
            (sha, t) for sha, t in shas_with_time if t <= end)
        shas_with_time = tuple(
            sorted(shas_with_time, key=lambda x: x[1], reverse=True))
        period_shas = tuple(sha for sha, t in shas_with_time if begin <= t)
        if not shas_with_time:
            stats[filename].update({
                'last_change': 0,
                'loc': 0,
                'lines': 0,
                'complexity': 0,
                'mean_complexity': 0,
                'complexity_sd': 0,
                'complexity_max': 0,
                'proximity': 0,
                'mean_proximity': 0,
                'proximity_sd': 0,
                'proximity_max': 0,
                'authors': ({}, 0)
            })
            continue
        last_sha, last_change_time = shas_with_time[0]

        proximity_stats = as_stats(
            'proximity',
            tuple(data['proximity']
                  for sha, data in full_stats[filename].items()
                  if sha in period_shas))
        stats[filename].update({
            'last_change':
            last_change_time,
            'loc':
            full_stats[filename][last_sha]['lines'],  # FIXME
            'lines':
            full_stats[filename][last_sha]['lines'],
            'complexity':
            full_stats[filename][last_sha]['complexity']['total'],
            'mean_complexity':
            full_stats[filename][last_sha]['complexity']['mean'],
            'complexity_sd':
            full_stats[filename][last_sha]['complexity']['sd'],
            'complexity_max':
            full_stats[filename][last_sha]['complexity']['max'],
            'proximity':
            proximity_stats.total,
            'mean_proximity':
            proximity_stats.mean(),
            'proximity_sd':
            proximity_stats.sd(),
            'proximity_max':
            proximity_stats.max_value(),
            'authors':
            git_log.get_main_authors(filename=filename)
        })

    return stats


class App:
    def __init__(self, config) -> None:
        self.__config = config
        self.git_log = GitLog(root=self.__config['path'],
                              commits=load_commits())

        today = datetime.now(tz=timezone.utc)
        period_start = today - timedelta(days=800)
        self.selected = []
        self.full_stats = load_stats()
        self.stats = {}
        self.module_stats = {}
        self.summary = Div(text='', width=CONTROL_WIDTH, height=100)

        self.file_analysis = FileAnalysis(git_log=self.git_log,
                                          selected_file='',
                                          begin=period_start,
                                          end=today,
                                          width=2 * CONTROL_WIDTH,
                                          height=CONTROL_WIDTH)

        self.source = ColumnDataSource(
            data=dict(x=[], y=[], module=[], revisions=[], size=[]))
        self.source.selected.on_change('indices', self.update_selected)  # pylint: disable=no-member
        self.x_menu = Select(title='X-Axis', value=COLUMNS[3], options=COLUMNS)
        self.x_menu.on_change('value', self.update_table)

        self.y_menu = Select(title='Y-Axis', value=COLUMNS[0], options=COLUMNS)
        self.y_menu.on_change('value', self.update_table)

        self.color = Select(title='Color', value=COLUMNS[6], options=COLUMNS)
        self.color.on_change('value', self.update_table)

        self.level = LEVELS[0]
        self.level_menu = Select(title='Level',
                                 value=LEVELS[0],
                                 options=LEVELS)
        self.level_menu.on_change('value', self.update_level)

        self.circ_pack_color = Select(title='Overview Color',
                                      value=CIRC_PACK_CRITERIA[1],
                                      options=CIRC_PACK_CRITERIA)
        self.circ_pack_color.on_change('value', self.update_circ_pack_color)

        self.range_slider = DateRangeSlider(
            start=self.git_log.first_commit_date(),
            end=today,
            step=1,
            value=(period_start, today),
            title='Range',
            width=CONTROL_WIDTH + PLOT_WIDTH - 100)

        self.range_button = Button(label="Select",
                                   button_type="default",
                                   width=50)
        self.range_button.on_click(self.update_date_range)

        self.plus_button = Button(label='+', button_type='default', width=50)
        self.plus_button.on_click(self.increase_dates)
        self.minus_button = Button(label='-', button_type='default', width=50)
        self.minus_button.on_click(self.decrease_dates)

        self.long_term_plot = LongTermPlot(stats=self.stats,
                                           git_log=self.git_log,
                                           period_start=period_start,
                                           period_end=today,
                                           width=PLOT_WIDTH,
                                           height=PLOT_HEIGHT)

        wordcloud = get_new_workcloud_plot(git_log=self.git_log,
                                           end=self.date_slider_value(),
                                           period=self.period_length(),
                                           width=PLOT_WIDTH)
        self.update_stats(period_start=period_start, period_end=today)
        self.update_source()
        self.circular_package = self.get_circular_package()
        controls = column(row(self.minus_button, self.plus_button),
                          self.summary,
                          wordcloud,
                          self.x_menu,
                          self.y_menu,
                          self.color,
                          self.circ_pack_color,
                          self.level_menu,
                          width=CONTROL_WIDTH)
        self.layout = column(
            row(self.range_slider, self.range_button),
            row(
                controls, self.create_figure()),
            row(self.circular_package.plot,
                       self.long_term_plot.layout)
        )
        self.update_wordcloud()
        self.update_summary()

    def increase_dates(self):
        start, end = self.range_slider.value
        start = ms_to_datetime(start)
        end = ms_to_datetime(end)
        dt = end - start
        new_end = end + dt
        if new_end > ms_to_datetime(self.range_slider.end):
            new_end = ms_to_datetime(self.range_slider.end)
            dt = new_end - end
        start += dt
        end = new_end
        self.range_slider.value = (1000 * start.timestamp(),
                                   1000 * end.timestamp())
        self.update_date_range()

    def decrease_dates(self):
        start, end = self.range_slider.value
        start = ms_to_datetime(start)
        end = ms_to_datetime(end)
        dt = end - start
        new_start = start - dt
        if new_start < ms_to_datetime(self.range_slider.start):
            new_start = ms_to_datetime(self.range_slider.start)
            dt = start - new_start
        start = new_start
        end -= dt
        self.range_slider.value = (1000 * start.timestamp(),
                                   1000 * end.timestamp())
        self.update_date_range()

    def get_stats(self):
        return self.stats

    def get_circ_color_data(self, value):
        if value == 'soc' and self.selected:

            selected_file = self.get_selected_file()
            begin, end = self.get_period_as_datetime()
            couplings, _ = self.git_log.get_couplings(filename=selected_file,
                                                      begin=begin,
                                                      end=end)

            def get_value(name):
                return 2 + 2 * couplings[
                    name] if name in couplings else 1 if name == selected_file else 0

            return {module: get_value(module) for module in self.get_stats()}

        if value == 'author':
            main_authors = {
                module: list(
                    self.git_log.get_main_authors(filename=module,
                                                  max_authors=1)[0].keys())[0]
                for module in self.get_stats()
            }
            indexed_main_authors = list(set(main_authors.values()))

            return {
                module: 3 * indexed_main_authors.index(main_authors[module])
                for module in self.get_stats()
            }

        if value == 'age':
            return get_age(self.get_stats(), inverse=True)

        if value == 'churn':
            return {
                name: sum(churn['added_lines'] + churn['removed_lines']
                          for churn in data['churn'])
                for name, data in self.get_stats().items()
            }

        if value == 'churn/line':
            return {
                name: min(
                    math.log(1 +
                             sum(churn['added_lines'] + churn['removed_lines']
                                 for churn in data['churn']) / data['lines']),
                    2)
                for name, data in self.get_stats().items()
            }

        return {
            module: data[value]
            for module, data in self.get_stats().items()
        }

    def update_level(self, attr, old, new):
        self.update_source()

    def update_circ_pack_color(self, attr, old, new):
        self.circular_package.update_package(self.get_circ_color_data(new),
                                             stats=self.get_stats())

    def get_circular_package(self):
        circ_data = translate_dict(csv_as_enclosure_json.run(
            self.get_stats()))['children']
        return CircularPackage(data=circ_data,
                               width=PLOT_HEIGHT,
                               height=PLOT_HEIGHT,
                               color_data=self.get_circ_color_data(
                                   self.circ_pack_color.value),
                               stats=self.get_stats(),
                               selected_callback=self.update_circ_selected)

    def date_slider_value(self):
        return ms_to_datetime(self.range_slider.value[1])

    def period_length(self):
        return ms_to_datetime(self.range_slider.value[1]) - ms_to_datetime(
            self.range_slider.value[0])

    def update_summary(self):
        n_changed = len([
            name for name, data in self.get_stats().items()
            if data['revisions'] > 0
        ])
        authors = set(author for data in self.get_stats().values()
                      for author in data['authors'][0])
        n_authors = len(authors)
        self.summary.text = f'Summary:</br>#files: {len(self.get_stats())}</br>#changed: {n_changed}</br>#authors: {n_authors}'

    def update_stats(self, period_start: datetime, period_end: datetime):
        t0 = time.time()
        self.stats = get_current_stats(full_stats=self.full_stats,
                                       git_log=self.git_log,
                                       begin=period_start,
                                       end=period_end)
        t1 = time.time()
        print(f'time: {t1 - t0}')
        self.module_stats = self.git_log.get_revisions_for_module(
            begin=period_start,
            end=period_end,
            module_map=get_module_map(self.__config))
        add_stats_for_module(module_stats=self.module_stats,
                             file_stats=self.get_stats(),
                             module_map=get_module_map(self.__config))
        self.update_summary()
        self.long_term_plot.update(stats=self.get_stats(),
                                   period_start=period_start,
                                   period_end=period_end)

    def update_wordcloud(self):
        wordcloud = get_new_workcloud_plot(git_log=self.git_log,
                                           end=self.date_slider_value(),
                                           period=self.period_length(),
                                           width=PLOT_WIDTH)
        self.layout.children[1].children[0].children[WORDCLOUD_IDX] = wordcloud  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

    def get_period_as_datetime(self):
        period_start, period_end = self.range_slider.value
        return ms_to_datetime(period_start), ms_to_datetime(period_end)

    def update_date_range(self):
        self.circular_package.reset_selection()
        period_start, period_end = self.get_period_as_datetime()
        self.update_stats(period_start=period_start, period_end=period_end)
        self.update_source()
        self.update_wordcloud()
        self.circular_package = self.get_circular_package()
        self.layout.children[1].children[1] = self.create_figure()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
        self.layout.children[2].children[0] = self.circular_package.plot  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

    def update_source(self):
        if self.level_menu.value == 'module':
            self.update_source_for_module()
        else:
            self.update_source_for_file()

    @timer
    def update_source_for_file(self):
        churn = [
            sum(churn['added_lines'] + churn['removed_lines']
                for churn in data['churn'])
            for data in self.get_stats().values()
        ]
        churn_per_line = [(sum(churn['added_lines'] + churn['removed_lines']
                               for churn in data['churn']) /
                           data['lines']) if data['lines'] else 99999.9
                          for data in self.get_stats().values()]
        color_data = []
        if self.color.value == 'churn':
            color_data = churn
        elif self.color.value == 'churn/line':
            color_data = [min(math.log(1 + val), 2) for val in churn_per_line]
        else:
            color_data = [
                data[self.color.value] for data in self.get_stats().values()
            ]

        def get_author(author, ratio):
            return f'{author} ({round(ratio,2)})'

        print(f'len {len(self.get_stats())}')

        self.source.data = dict(
            module=list(self.get_stats().keys()),
            loc=[data['loc'] for data in self.get_stats().values()],
            revisions=[
                data['revisions'] for data in self.get_stats().values()
            ],
            size=[
                9 + 0.2 * float(data['loc'])
                for data in self.get_stats().values()
            ],
            lines=[data['lines'] for data in self.get_stats().values()],
            complexity=[
                data['complexity'] for data in self.get_stats().values()
            ],
            mean_complexity=[
                data['mean_complexity'] for data in self.get_stats().values()
            ],
            complexity_sd=[
                data['complexity_sd'] for data in self.get_stats().values()
            ],
            complexity_max=[
                data['complexity_max'] for data in self.get_stats().values()
            ],
            proximity=[
                data['proximity'] for data in self.get_stats().values()
            ],
            mean_proximity=[
                data['mean_proximity'] for data in self.get_stats().values()
            ],
            proximity_sd=[
                data['proximity_sd'] for data in self.get_stats().values()
            ],
            proximity_max=[
                data['proximity_max'] for data in self.get_stats().values()
            ],
            soc=[data['soc'] for data in self.get_stats().values()],
            color=get_colors(color_data),
            authors=[
                ', '.join(
                    get_author(author, ratio)
                    for author, ratio in self.git_log.get_main_authors(
                        filename=filename)[0].items())
                for filename in self.get_stats()
            ],
            n_authors=[
                self.get_stats()[name]['authors'][1]
                for name in self.get_stats()
            ],
            age=list(get_age(self.get_stats()).values()),
            churn_overview=[
                f"{sum(churn['added_lines'] + churn['removed_lines'] for churn in data['churn'])}:{sum(churn['added_lines'] for churn in data['churn'])}:{sum(churn['removed_lines'] for churn in data['churn'])}"
                for data in self.get_stats().values()
            ],
            churn=churn,
            churn_per_line=churn_per_line)

    @timer
    def update_source_for_module(self):
        stats = self.module_stats
        churn = [
            sum(churn['added_lines'] + churn['removed_lines']
                for churn in data['churn']) for data in stats.values()
        ]
        for f, d in stats.items():
            if d['lines'] == 0:
                print(f'no lines in {f}')
        churn_per_line = [
            sum(churn['added_lines'] + churn['removed_lines']
                for churn in data['churn']) / data['lines']
            for data in stats.values()
        ]
        color_data = []
        if self.color.value == 'churn':
            color_data = churn
        elif self.color.value == 'churn/line':
            color_data = churn_per_line
        else:
            color_data = [data[self.color.value] for data in stats.values()]

        sizes = [
            9 + 0.5 * math.sqrt(float(data['loc'])) for data in stats.values()
        ]

        def get_author(author, ratio):
            return f'{author} ({round(ratio,2)})'

        self.source.data = dict(
            module=list(stats.keys()),
            loc=[data['loc'] for data in stats.values()],
            revisions=[data['revisions'] for data in stats.values()],
            size=sizes,
            lines=[data['lines'] for data in stats.values()],
            complexity=[data['complexity'] for data in stats.values()],
            mean_complexity=[
                data['mean_complexity'] for data in stats.values()
            ],
            complexity_sd=[data['complexity_sd'] for data in stats.values()],
            complexity_max=[data['complexity_max'] for data in stats.values()],
            proximity=[data['proximity'] for data in stats.values()],
            mean_proximity=[data['mean_proximity'] for data in stats.values()],
            proximity_sd=[data['proximity_sd'] for data in stats.values()],
            proximity_max=[data['proximity_max'] for data in stats.values()],
            soc=[data['soc'] for data in stats.values()],
            color=get_colors(color_data),
            authors=[
                '' for _ in stats
                # ', '.join(
                #     get_author(author, ratio)
                #     for author, ratio in self.git_log.get_main_authors(
                #         filename=filename)[0].items()) for filename in stats
            ],
            n_authors=['' for _ in stats],
            # n_authors=[stats[filename]['authors'][1] for filename in stats],
            age=list(get_age(stats).values()),
            churn_overview=[
                f"{sum(churn['added_lines'] + churn['removed_lines'] for churn in data['churn'])}:{sum(churn['added_lines'] for churn in data['churn'])}:{sum(churn['removed_lines'] for churn in data['churn'])}"
                for data in stats.values()
            ],
            churn=churn,
            churn_per_line=churn_per_line)

    @timer
    def create_figure(self):
        self.update_source()
        x_title = self.x_menu.value
        y_title = self.y_menu.value
        if x_title == 'churn/line':
            x_title = 'churn_per_line'
        if y_title == 'churn/line':
            y_title = 'churn_per_line'

        kw = dict(
            title="",
            tooltips=[('Module', '@module'), ('LOC', '@loc'),
                      ('#rev', '@revisions'), ('lines', '@lines'),
                      ('complexity', '@complexity'),
                      ('mean_complexity', '@mean_complexity'),
                      ('complexity_sd', '@complexity_sd'),
                      ('complexity_max', '@complexity_max'),
                      ('proximity', '@proximity'),
                      ('mean_proximity', '@mean_proximity'),
                      ('proximity_sd', '@proximity_sd'),
                      ('proximity_max', '@proximity_max'), ('SOC', '@soc'),
                      ('authors', '@authors'), ('#authors', '@n_authors'),
                      ('age', '@age days'), ('churn', '@churn_overview')],
            x_axis_label=x_title,
            y_axis_label=y_title,
            y_axis_type='log' if y_title == 'revisions' else 'linear',
        )
        p = figure(plot_width=PLOT_WIDTH,
                   plot_height=PLOT_HEIGHT,
                   tools='pan,wheel_zoom,hover,reset,tap',
                   **kw)
        p.toolbar.logo = None
        if y_title == 'revisions':
            p.y_range.start = 0.8

        p.circle(x=x_title,
                 y=y_title,
                 source=self.source,
                 color='color',
                 size='size',
                 line_color="white",
                 alpha=0.6,
                 hover_color='white',
                 hover_alpha=0.5)
        return p

    def get_selected_file(self):
        return self.source.data['module'][self.selected[0]]

    def update_table(self, attr, old, new):
        self.layout.children[1].children[1] = self.create_figure()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

    def update_circ_selected(self):
        if not self.circular_package.current_idx:
            self.source.selected.indices = []
            return
        name = self.circular_package.full_names[
            self.circular_package.current_idx]
        try:
            idx = self.source.data['module'].index(name)
        except ValueError:
            self.source.selected.indices = []
        else:
            self.source.selected.indices = [idx]

    def update_selected(self, attr, old, new):
        self.selected = new
        if self.selected:
            begin, end = self.get_period_as_datetime()
            self.file_analysis.set_selected_file(
                selected_file=self.get_selected_file(), begin=begin, end=end)
        if len(self.layout.children[1].children) == 3:  # pylint: disable=unsubscriptable-object
            if self.selected:
                self.layout.children[1].children[  # pylint: disable=unsubscriptable-object
                    2] = self.file_analysis.get_plot()
            else:
                del self.layout.children[1].children[2]  # pylint: disable=unsupported-delete-operation,unsubscriptable-object
        if len(self.layout.children[1].children) == 2 and self.selected:  # pylint: disable=unsubscriptable-object
            self.layout.children[1].children.append(  # pylint: disable=no-member,unsubscriptable-object
                self.file_analysis.get_plot())
        if self.circ_pack_color.value == 'soc':
            self.update_circ_pack_color('value', '',
                                        self.circ_pack_color.value)


MIN_DATUM = 0.0


def translate_dict(d):
    new_d = {
        'id': d['name'],
    }
    if 'children' in d and d['children']:
        new_d['children'] = [translate_dict(c) for c in d['children']]
    if d.get('size') is not None:
        new_d['datum'] = max(float(d.get('size')), 1e-3)
    else:
        new_d['datum'] = sum(child['datum'] for child in new_d['children'])
    new_d['datum'] = max(new_d['datum'], MIN_DATUM)
    return new_d


def get_config():
    with open('crimescene/.config', 'r') as config_file:
        config = json.loads(config_file.read())
        config['stats_path'] = f'{HOME}/.stats/{config["project"]}'
        if not config['path'].endswith('/'):
            config['path'] += '/'
        return config


print(f'CONFIG: {get_config()}')
app = App(config=get_config())
curdoc().add_root(app.layout)
curdoc().title = "Crime Scene"
