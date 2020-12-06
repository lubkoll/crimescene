import json
import sqlite3

DB_PATH = "cache.db"


class SQL:
    def __init__(self, path=DB_PATH) -> None:
        self._path = path
        self._connection = None
        self._cursor = None
        self.create_table()

    def _connect(self):
        self._connection = sqlite3.connect(DB_PATH)
        self._cursor = self._connection.cursor()

    def _disconnect(self):
        self._connection.commit()
        self._connection.close()
        self._connection = None
        self._cursor = None

    def create_table(self):
        self._connect()
        self._cursor.execute(
            'CREATE TABLE IF NOT EXISTS projects(project TEXT)')
        self._disconnect()

    def add_project(self, project_name: str):
        self._connect()
        self._cursor.execute(
            f'CREATE TABLE IF NOT EXISTS {project_name}(start INTEGER NOT NULL, end INTEGER NOT NULL, stats JSON NOT NULL)'
        )
        is_present = self._cursor.execute(
            f'SELECT project FROM projects WHERE project = ?',
            (project_name, )).fetchone()
        print(f'is {project_name} present: {is_present is not None}')
        if not is_present:
            print(f'Add {project_name}')
            self._cursor.execute('INSERT INTO projects(project) VALUES (?)',
                                 (project_name, ))
        self._disconnect()

    def store_stats(self, project_name: str, start: int, end: int, stats):
        self._connect()
        is_present = self._cursor.execute(
            f'SELECT start, end FROM {project_name} WHERE start = ? AND end = ?',
            (start, end)).fetchone()
        if is_present:
            print(
                f'{project_name}:{start}-{end} already present. Skipping insert.'
            )
            return

        cmd = f'INSERT INTO {project_name}(start, end, stats) VALUES(?,?,?,?)'
        self._cursor.execute(cmd, (start, end, json.dumps(stats)))
        self._disconnect()

    def read_stats(self, project_name: str):
        self._connect()
        stat_rows = self._cursor.execute(
            f'SELECT start, end, stats FROM {project_name}').fetchall()
        stats = {tuple(row[0:2]): json.loads(row[2]) for row in stat_rows}
        self._disconnect()
        return stats