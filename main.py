from collections import defaultdict
from dataclasses import dataclass
import json
import re
from stats_cache import load_commits, load_stats
from get_wordcloud import get_new_workcloud_plot
from git_log import GitLog, get_files_in_commit, get_first_commit_date
from file_analysis import FileAnalysis
from get_db import SQL
from util import ms_to_datetime, to_days, DATE_FORMAT
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
from process_git_log import get_loc, add_loc, read_locs

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


def add_stats_for_module(module_stats, file_stats, module_map):
    for filename, data in file_stats.items():
        module = module_map(filename)
        module_stats[module]['loc'] += data['loc']
        module_stats[module]['lines'] += data['lines']
        module_stats[module]['complexity'] += data['complexity']
        module_stats[module]['complexity_max'] = max(
            module_stats[module].get('complexity_max', 0), data['complexity'])
    for data in module_stats.values():
        data['mean_complexity'] = data['complexity'] / data['lines']


def get_current_stats(full_stats, git_log: GitLog, begin: datetime,
                      end: datetime):
    stats = git_log.get_revisions_only(begin=begin, end=end)
    files = git_log.get_files_in_repository()
    to_remove = [key for key in stats if key not in files]
    for key in to_remove:
        del stats[key]
    for filename, data in full_stats.items():
        if filename not in stats or filename not in files:
            continue
        shas_with_time = [(sha, git_log.get_time_from_sha(sha))
                          for sha in data.keys()]
        shas_with_time = [(sha, t) for sha, t in shas_with_time if t <= end]
        shas_with_time = list(
            sorted(shas_with_time, key=lambda x: x[1], reverse=True))
        if not shas_with_time:
            continue
        last_sha, last_change_time = shas_with_time[0]
        if full_stats[filename][last_sha]['lines'] == 0:
            if filename in stats:
                del stats[filename]
            continue

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
            0,
            'mean_proximity':
            0,
            'proximity_sd':
            0,
            'proximity_max':
            0,
            'authors':
            git_log.get_main_authors(filename=filename)
            #            list(set(commit.author for commit in commits))
        })

    git_log.add_proximity_analysis(begin=begin, end=end, stats=stats)

    return stats


class App:
    def __init__(self, config) -> None:
        self.__config = config
        self.git_log = GitLog(root=self.__config['path'],
                              commits=load_commits())

        today = datetime.now(tz=timezone.utc)
        period_start = today - timedelta(days=800)
        #        self.git_log = GitLog.from_dir(self.__config['path'])
        self.selected = []
        # self.db = SQL()
        # self.db.add_project(project_name=self.__config['project'])
        # stats = self.db.read_stats(project_name=self.__config['project'])
        self.full_stats = load_stats()
        self.stats = get_current_stats(full_stats=self.full_stats,
                                       git_log=self.git_log,
                                       begin=period_start,
                                       end=today)
        self.start_loc = 0
        self.summary = Div(text='', width=CONTROL_WIDTH, height=100)

        # self.module_stats = self.git_log.get_revisions_for_module(
        #     begin=period_start,
        #     end=today,
        #     module_map=get_module_map(self.__config))
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

        self.long_term_plot_menu = Select(title='Long Term Plot',
                                          value='churn',
                                          options=['churn', 'rising hotspot'])
        self.long_term_plot_menu.on_change('value', self.update_long_term_plot)
        self.long_term_plot_criterion = Select(
            title='Long Term Plot Criterion',
            value=LONG_TERM_PLOT_CRITERIA[0],
            options=LONG_TERM_PLOT_CRITERIA)
        self.long_term_plot_criterion.on_change('value',
                                                self.update_long_term_plot)

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
                          self.long_term_plot_menu,
                          self.long_term_plot_criterion,
                          width=CONTROL_WIDTH)
        self.layout = column(
            row(self.range_slider, self.range_button),
            row(
                controls,
                column(self.create_figure(), self.circular_package.plot,
                       self.create_churn_plot())),
        )
        self.update_wordcloud()
        self.update_summary()

    def update_long_term_plot(self, attr, old, new):
        self.layout.children[1].children[1].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
            2] = self.create_churn_plot()

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

    def add_repo_main_authors(self, max_authors: int = 3):
        for module, data in self.get_stats().items():
            data['authors'] = self.git_log.get_main_authors(
                filename=module, max_authors=max_authors)
        # for module, data in self.module_stats.items():
        #     data['authors'] = self.git_log.get_main_authors(
        #         filename=module,
        #         max_authors=max_authors,
        #         module_map=get_module_map(self.__config))

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
        print(f'authors {list(authors)}')
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
        self.update_summary()

        # if self.range_slider.value in self.stats:
        #     self.update_summary()
        #     #            self.start_loc = get_lines_before(root=self.__config['path'], before=period_start)
        #     self.start_loc = sum(
        #         read_locs(
        #             get_loc(
        #                 root=self.__config['path'],
        #                 before=period_start.strftime(DATE_FORMAT))).values())
        #     return
        # t1 = time.time()
        # stats = self.git_log.get_revisions(begin=period_start, end=period_end)
        # # self.module_stats = self.git_log.get_revisions_for_module(
        # #     begin=period_start,
        # #     end=period_end,
        # #     module_map=get_module_map(self.__config))
        # #        self.start_loc = get_lines_before(root=self.__config['path'], before=period_start)
        # self.start_loc = sum(
        #     read_locs(
        #         get_loc(root=self.__config['path'],
        #                 before=period_start.strftime(DATE_FORMAT))).values())
        # print(f'START LOC {self.start_loc}')
        # t2 = time.time()
        # self.stats[self.range_slider.value] = stats
        # t3 = time.time()
        # locs = get_loc(root=self.__config['path'],
        #                before=period_end.strftime(DATE_FORMAT))
        # add_loc(self.get_stats(), locs)
        # t4 = time.time()
        # self.git_log.add_complexity_analysis(
        #     end=period_end.strftime(DATE_FORMAT), stats=self.get_stats())
        # t5 = time.time()
        # self.git_log.add_proximity_analysis(begin=period_start,
        #                                     end=period_end,
        #                                     stats=self.get_stats())
        # self.add_repo_main_authors()

        # # add_stats_for_module(module_stats=self.module_stats,
        # #                      file_stats=self.get_stats(),
        # #                      module_map=get_module_map(self.__config))
        # t6 = time.time()
        # self.update_summary()
        # t7 = time.time()
        # print(f'{t2-t1}, {t3-t2}, {t4-t3}, {t5-t4}, {t6-t5}, {t7-t6}')
        # self.db.store_stats(project_name=self.__config['project'],
        #                     start=self.range_slider.value[0],
        #                     end=self.range_slider.value[1],
        #                     stats=stats)

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
        self.layout.children[1].children[1].children[0] = self.create_figure()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
        self.layout.children[1].children[1].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
            1] = self.circular_package.plot
        self.layout.children[1].children[1].children[  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object
            2] = self.create_churn_plot()

    def update_source(self):
        if self.level_menu.value == 'module':
            self.update_source_for_module()
        else:
            self.update_source_for_file()

    def update_source_for_file(self):
        churn = [
            sum(churn['added_lines'] + churn['removed_lines']
                for churn in data['churn'])
            for data in self.get_stats().values()
        ]
        churn_per_line = [
            sum(churn['added_lines'] + churn['removed_lines']
                for churn in data['churn']) / data['lines']
            for data in self.get_stats().values()
        ]
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
                # ', '.join(
                #     get_author(author, ratio) for author, ratio in
                #     self.get_stats()[name]['authors'][0].items())
                # for name in self.get_stats()
                #self.get_stats()[name]['authors'] for name in self.get_stats()
                # 'me' for name in self.get_stats()
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

    def update_source_for_module(self):
        pass
        # stats = self.module_stats
        # churn = [
        #     sum(churn['added_lines'] + churn['removed_lines']
        #         for churn in data['churn']) for data in stats.values()
        # ]
        # churn_per_line = [
        #     sum(churn['added_lines'] + churn['removed_lines']
        #         for churn in data['churn'])  # / data['lines']
        #     for data in stats.values()
        # ]
        # color_data = []
        # if self.color.value == 'churn':
        #     color_data = churn
        # elif self.color.value == 'churn/line':
        #     color_data = churn_per_line
        # else:
        #     color_data = [data[self.color.value] for data in stats.values()]

        # sizes = [
        #     9 + 0.5 * math.sqrt(float(data['loc'])) for data in stats.values()
        # ]

        # def get_author(author, ratio):
        #     return f'{author} ({round(ratio,2)})'

        # self.source.data = dict(
        #     module=list(stats.keys()),
        #     loc=[data['loc'] for data in stats.values()],
        #     revisions=[data['revisions'] for data in stats.values()],
        #     size=sizes,
        #     lines=[data['lines'] for data in stats.values()],
        #     complexity=[data['complexity'] for data in stats.values()],
        #     mean_complexity=[
        #         data['mean_complexity'] for data in stats.values()
        #     ],
        #     complexity_sd=[data['complexity_sd'] for data in stats.values()],
        #     complexity_max=[data['complexity_max'] for data in stats.values()],
        #     soc=[data['soc'] for data in stats.values()],
        #     color=get_colors(color_data),
        #     authors=[
        #         ', '.join(
        #             get_author(author, ratio)
        #             for author, ratio in data['authors'][0].items())
        #         for data in stats.values()
        #     ],
        #     n_authors=[data['authors'][1] for data in stats.values()],
        #     age=list(get_age(stats).values()),
        #     churn_overview=[
        #         f"{sum(churn['added_lines'] + churn['removed_lines'] for churn in data['churn'])}:{sum(churn['added_lines'] for churn in data['churn'])}:{sum(churn['removed_lines'] for churn in data['churn'])}"
        #         for data in stats.values()
        #     ],
        #     churn=churn,
        #     churn_per_line=churn_per_line)

    def get_churn(self, t, key):
        return sum(churn[key] for data in self.get_stats().values()
                   for churn in data['churn']
                   if t == datetime.fromtimestamp(churn['timestamp'],
                                                  tz=timezone.utc).date())

    def get_time_axis(self):
        start_date = ms_to_datetime(self.range_slider.value[0])
        end_date = self.date_slider_value()
        n_days = int(to_days(end_date - start_date))
        return [start_date + timedelta(days=t) for t in range(1, n_days + 1)]

    def create_churn_plot(self):
        p = figure(title=self.long_term_plot_menu.value,
                   x_axis_label='date',
                   y_axis_label='loc' if self.long_term_plot_menu.value
                   == 'churn' else 'mean complexity',
                   x_axis_type='datetime',
                   plot_width=PLOT_WIDTH,
                   plot_height=PLOT_HEIGHT,
                   tools='pan,xwheel_zoom,reset')
        x = []
        if self.long_term_plot_menu.value == 'churn':
            x = self.get_time_axis()
            added = [self.get_churn(t.date(), key='added_lines') for t in x]
            removed = [
                self.get_churn(t.date(), key='removed_lines') for t in x
            ]
            locs = [self.start_loc]
            for idx in range(len(x) - 1):
                locs.append(locs[idx] + added[idx] - removed[idx])
            p.line(x=x, y=added, color='orange', legend_label='added')
            p.line(x=x, y=removed, color='blue', legend_label='removed')
            p.line(x=x, y=locs, color='gray', legend_label='lines of code')
        if self.long_term_plot_menu.value == 'rising hotspot':
            period_start, period_end = self.get_period_as_datetime()
            complexity_trends = {
                filename: self.git_log.compute_complexity_trend(
                    filename=filename,
                    begin=
                    period_start,  #get_first_commit_date(root=self.__config['path']),
                    end=period_end)
                for filename in self.get_stats()
            }
            initial_complexities = []
            final_complexities = []
            stats_idx = 2
            if self.long_term_plot_criterion.value == 'mean complexity':
                stats_idx = 3
            if self.long_term_plot_criterion.value == 'complexity sd':
                stats_idx = 4
            if self.long_term_plot_criterion.value == 'lines':
                stats_idx = 1
            for filename, data in complexity_trends.items():
                if data:
                    initial_complexities.append((filename, data[0][stats_idx]))
                    final_complexities.append((filename, data[-1][stats_idx]))

            initial_complexities.sort(key=lambda x: x[1], reverse=True)
            final_complexities.sort(key=lambda x: x[1], reverse=True)
            c0 = {
                filename: idx
                for idx, (filename, _) in enumerate(initial_complexities)
            }
            c1 = {
                filename: idx
                for idx, (filename, _) in enumerate(final_complexities)
            }
            rank_changes = [(filename, c0[filename] - c1[filename])
                            for filename in c0]

            rank_changes.sort(key=lambda x: x[1], reverse=True)
            rank_changes = rank_changes[:10]
            color_data = get_colors([rank for _, rank in rank_changes])
            x = list(
                set(
                    self.git_log.get_commit_from_sha(row[0]).creation_time
                    for filename, _ in rank_changes
                    for row in complexity_trends[filename]))
            x.sort()
            for (filename, rank_change), color in zip(rank_changes,
                                                      color_data):
                trend = complexity_trends[filename]
                previous = 0

                def get_value(t):
                    nonlocal previous
                    for row in trend:
                        if self.git_log.get_commit_from_sha(
                                row[0]).creation_time == t:
                            previous = row[stats_idx]
                            return row[stats_idx]
                    return previous

                y = [get_value(t) for t in x]

                p.line(x=x,
                       y=y,
                       color=color,
                       legend_label=filename + ' ' + str(rank_change))

        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        return p

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
        self.layout.children[1].children[1].children[0] = self.create_figure()  # pylint: disable=unsupported-assignment-operation,unsubscriptable-object

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
