from datetime import datetime, timedelta

from wordcloud import WordCloud, STOPWORDS
from bokeh.plotting import figure
from util import to_days
from git_log import GitLog, DATE_FORMAT

PROJECT_STOPWORDS = set()


def wordcloud_file(end: str, period: timedelta):
    return f'crimescene/static/wordcloud_{end}_{to_days(period)}.png'


def generate_wordcloud(git_log: GitLog, end: datetime, period: timedelta):
    text = ' '.join(git_log.commit_msg(begin=end - period,
                                       end=end)).replace("'", "")
    wordcloud = WordCloud(stopwords=STOPWORDS | PROJECT_STOPWORDS,
                          background_color='white')
    wordcloud.generate(text)
    wordcloud.to_file(
        wordcloud_file(end=end.strftime(DATE_FORMAT), period=period))


def get_workcloud_plot(end: datetime, period: timedelta, width):
    wordcloud = figure(x_range=(0, 1),
                       y_range=(0, 1),
                       plot_width=width,
                       plot_height=250,
                       tools='')
    wordcloud.toolbar.logo = None
    wordcloud.toolbar_location = None
    wordcloud.xaxis.visible = None
    wordcloud.yaxis.visible = None
    wordcloud.xgrid.grid_line_color = None
    wordcloud.ygrid.grid_line_color = None
    wordcloud.outline_line_alpha = 0
    wordcloud.image_url(
        url=[wordcloud_file(end=end.strftime(DATE_FORMAT), period=period)],
        x=0,
        y=1)
    return wordcloud


def get_new_workcloud_plot(git_log: GitLog, end: datetime, period: timedelta,
                           width: int):
    generate_wordcloud(git_log=git_log, end=end, period=period)
    return get_workcloud_plot(end=end, period=period, width=width)