import torndb

import logging

from main.helper import *


class ShowStatus(myRequestHandler):
    @web.removeslash
    def get(self):
        result = {}
        try:
            self.db.get('SELECT MAX(id) FROM entity;')
            self.json({
                'result': True,
                'time': round(self.request.request_time(), 3)
            })
        except Exception, e:
            self.json({
                'error': e,
                'time': round(self.request.request_time(), 3)
            }, 500)


class ShowDbSizes(myRequestHandler):
    @web.removeslash
    def get(self):
        result = {}
        for s in self._app_settings.values():
            db_connection = torndb.Connection(
                host        = s['database-host'],
                database    = s['database-name'],
                user        = s['database-user'],
                password    = s['database-password'],
            )
            size = db_connection.get('SELECT SUM(table_rows) AS table_rows,  SUM(data_length) AS data_length, SUM(index_length) AS index_length FROM information_schema.TABLES;')
            result[s['database-name']] = {
                'total': size.data_length+size.index_length,
                'data': size.data_length,
                'index': size.index_length,
            }

        self.json(result)


class ShowFileSizes(myRequestHandler):
    @web.removeslash
    def get(self):
        days = self.get_argument('days', default=7, strip=True),

        series_data = {}
        for s in self._app_settings.values():
            db_connection = torndb.Connection(
                host        = s['database-host'],
                database    = s['database-name'],
                user        = s['database-user'],
                password    = s['database-password'],
            )
            files = db_connection.get("""
                SELECT
                    SUM(filesize) AS filesize,
                    DATE_FORMAT(created, '%%Y-%%m-%%d') AS date
                FROM file
                GROUP BY
                    DATE_FORMAT(created, "%%Y-%%m-%%d")
                ORDER BY date DESC
                ;""")

            series_data.setDefault(s['database-name'], {})['name'] = s['database-name']
            series_data.setDefault(s['database-name'], {}).setDefault('data', []).push([files.date, files.filesize])

        self.json({
            'x_axis': {
                'type': 'datetime'
            },
            'series': series_data.values()
        })


handlers = [
    (r'/status', ShowStatus),
    (r'/status/dbsize', ShowDbSizes),
    (r'/status/filesize', ShowFileSizes),
]
