# encoding: utf-8
import logging, inspect, collections
import os.path

from django.core.management.base import BaseCommand
from django.conf import settings
from django.test import Client
from django.db import connection

class CountLogMessages(logging.Handler):
    def __init__(self, command_obj):
        logging.Handler.__init__(self)      # have to call this, can't use super(…)

        self.filehits = []
        self.sql_stmt_type_hits = collections.defaultdict(int)
        self.queries = []

        self.command_obj = command_obj

    def is_file_to_be_included(self, filename):
        if filename == __file__:
            return False

        return self.command_obj.is_file_to_be_included(filename)

    def emit(self, record):
        sql_duration = record.duration
        sql_stmt_type = record.sql.split(" ")[0]       # Is this a 'SELECT'? or 'INSERT' or …?
        self.sql_stmt_type_hits[sql_stmt_type] += 1
        sql_params = record.params
        sql_tables = []

        raw_sql = record.sql

        # Turn off SQL logging, otherwise this will cause an infinite loop by
        # calling this function again when it logs the 'explain' query
        settings.DEBUG = False
        cursor = connection.cursor()
        try:
            cursor.execute("EXPLAIN "+raw_sql)
        except Exception as ex:
            if sql_stmt_type != 'SELECT':
                # If this is pre-mysql 5.6, EXPLAIN can only do SELECT, 5.6+ it
                # can explain others. So we can't profile/explain this query.
                # So just pretend that there is 0. This makes "sum(…)" results
                # later sensible
                sql_num_tables = 0
                sql_num_rows = 0
            else:
                # Unexpected error, raise to fail fast
                raise
        else:
            sql_queryplan = cursor.fetchall()
            # MySQL explain column output:
            # id, select_type, table, type, possible_keys, key, key_len, ref, rows, Extra

            sql_num_tables = len(sql_queryplan)     # one row per table joined

            sql_tables = [row[2] for row in sql_queryplan if row[2] is not None]

            # If the 'Extra' (row[8]) is 'Impossible WHERE noticed after
            # reading const tables' (or "Impossible WHERE'), that means that MySQL has looked at the
            # SQL and seen that it cannot match (using an index or something).
            # i.e. this query will go very quickly, so pretend it's zero by
            # ignoring that row.
            results_with_rows = [x for x in sql_queryplan if x[9] not in
                ('Impossible WHERE noticed after reading const tables',
                 'Impossible WHERE',
                 'Select tables optimized away' ) ]
            # Remove UNION rows aswell cause they have no data
            results_with_rows = [x for x in results_with_rows if not (x[8] is None and x[1] in
                ('UNION RESULT',) ) ]
            
            # If this assert fails, either there's a bug, or it's not excluding useless rows that it should.
            assert all(x[8] is not None for x in results_with_rows), repr(results_with_rows)
            sql_num_rows = sum(row[8] for row in results_with_rows)
        finally:
            # If there's an error, be sure to turn on DEBUG again, otherwise
            # the first error will permanently turn off the logging
            settings.DEBUG = True

        print ""    # blank line between 'queries'

        this_stack = []
        for frame_details in inspect.stack():
            filename = frame_details[1]

            # We only want to include /our/ files, otherwise there is loads of django stuff.
            # But we want to exclude /this/ file (measure_sql_performance.py)
            if self.is_file_to_be_included(filename):
                lineno = frame_details[2]

                # At each SQL call, at each frame on the stack, we store:
                # filename - filename of where we are
                # lineno - linenumber of the where we are
                # func_name - name of the function we're in
                # func_start_lineno - the line number of where this function starts (in filename obv.)
                # raw_sql - the SQL query with parameter placeholders
                # sql_params - the parameters for the SQL query
                # sql_duration - how many seconds this query took
                # sql_stmt_type - first word of SQL (e.g. 'SELECT'/'UPDATE')
                # sql_num_tables - How many tables were used 
                stack_summary = {
                    'filename':filename, 'lineno':lineno,
                    'func_start_lineno':frame_details[0].f_code.co_firstlineno, 'func_name':frame_details[3],
                    'raw_sql': raw_sql, 'sql_duration': sql_duration, 'sql_stmt_type': sql_stmt_type, 'sql_params': sql_params,
                    'sql_num_tables': sql_num_tables, 'sql_num_rows': sql_num_rows,
                    }
                self.filehits.append(stack_summary)
                this_stack.append(stack_summary)
                print "{func_name:>30} @ {filename:>40}:L{lineno:<5} (function starts at L{func_start_lineno:<5})".format(**stack_summary)

        print "Query used {sql_num_tables:>5} tables in {sql_duration:8.2f} sec and needed to look at {sql_num_rows:>5} rows".format(sql_duration=sql_duration, sql_num_rows=sql_num_rows, sql_num_tables=sql_num_tables)
        print "Query used {sql_num_tables:>5} tables: {tables}".format(sql_num_tables=sql_num_tables, tables=", ".join(sql_tables))
        print raw_sql, sql_params

        self.queries.append({
            'raw_sql': raw_sql, 'params': sql_params, 'duration': sql_duration, 'num_tables': sql_num_tables, 'num_rows': sql_num_rows,
            'calling_stack': this_stack,
        })


def most_common(items, count):
    """
    Given a list of items, return the top 'count' items in a list like so: [ (occurances, item), (occurances, items), … ]
    This is like py2.7's collections.Counter.most_common
    """
    counter = collections.defaultdict(int)
    for i in items:
        if isinstance(i, basestring):
            num = 1
            key = i
        else:
            num = i[0]
            key = i[1]

        counter[key] += num

    return [x for x in sorted([(counter[x], x) for x in counter], reverse=True)[:count]]

def splitpath(path, maxdepth=20):
    # Copied from http://nicks-liquid-soapbox.blogspot.ie/2011/03/splitting-path-to-list-in-python.html
    # Python has no decent os.path.split :(
    ( head, tail ) = os.path.split(path)
    return splitpath(head, maxdepth - 1) + [ tail ] \
        if maxdepth and head and head != path \
        else [ head or tail ]
    
class MeasureSQLCommand(BaseCommand):

    def set_up(self):
        # Django won't log SQL if DEBUG is False
        settings.DEBUG = True

        # Attach out log_counter to the django.db.backends thingie
        self.logger = logging.getLogger("django.db.backends")
        self.logger.setLevel(logging.DEBUG)
        self.log_counter = CountLogMessages(command_obj=self)
        self.logger.addHandler(self.log_counter)

        self.set_up_client()

    def is_file_to_be_included(self, filename):
        path_of_this_class = inspect.getfile(self.__class__)

        # The path of the command will probably be /a/b/c/d/$APPNAME/management/commands/commandname.py
        # We want to get to /a/b/c/d (which is probably the django project directory)
        poss_django_project_root = os.path.join(*splitpath(path_of_this_class)[:-4])


        # Not 100% accurate, since this could be /home/something/project and a
        # file in /home/something/projectextras/foo.py would match, it doesn't
        # add a trailing separator. Can't find a decent is-subdirectory
        # function. This should be good enough
        return filename.startswith(poss_django_project_root)

    def set_up_client(self):
        # We need a django test client
        self.client = Client()

    def handle(self, *args, **kwargs):
        self.set_up()

        self.inner_handle(*args, **kwargs)

        self.print_stats()

    def print_stats(self):

        if len(self.log_counter.filehits) == 0 and len(self.log_counter.queries) == 0:
            print "(no sql queries logged)"
            return

        print "\nAggregate statistics:"
        num_to_show = 20

        print "\nTop %d files:" % num_to_show
        print "\n".join("{0:>5} {1}".format(num, string) for num, string in most_common([x['filename'] for x in self.log_counter.filehits], num_to_show))
        print "\nTop %d lines:" % num_to_show
        print "\n".join("{0:>5} {1}".format(num, string) for num, string in most_common(["{0}:L{1}".format(x['filename'], x['lineno']) for x in self.log_counter.filehits], num_to_show))
        print "\nTop %d functions:" % num_to_show
        print "\n".join("{0:>5} {1}".format(num, string) for num, string in most_common(["{1} in {0} (L{2})".format(x['filename'], x['func_name'], x['func_start_lineno']) for x in self.log_counter.filehits], num_to_show))
        print "\nTop SQL statment types:"
        print "\n".join(sorted(("{0:>5} {1}".format(value, key) for key, value in self.log_counter.sql_stmt_type_hits.items()), reverse=True))

        print "\nTop 20 queries by number of rows looked at:"
        for count, (query, params) in sorted(((x['num_rows'], (x['raw_sql'], x['params'])) for x in self.log_counter.queries), key=lambda x:x[0], reverse=True)[:20]:
            print "{0:>7} {1} {2}".format(count, query[:100], params)
        print "\nTop 10 queries by number of table joins:"
        for count, (query, params) in sorted(((x['num_tables'], (x['raw_sql'], x['params'])) for x in self.log_counter.queries), key=lambda x:x[0], reverse=True)[:10]:
            print "{0:>7} {1} {2}".format(count, query[:100], params)
        print "\nTop 10 queries by SQL duration:"
        for count, (query, params) in sorted(((x['duration'], (x['raw_sql'], x['params'])) for x in self.log_counter.queries), key=lambda x:x[0], reverse=True)[:10]:
            print "{0:10.4f} {1} {2}".format(count, query[:100], params)

        print "\nTop %d files by number of rows looked at:" % num_to_show
        print "\n".join("{0:>7} {1}".format(num, string) for num, string in most_common([(x['sql_num_rows'], x['filename']) for x in self.log_counter.filehits], num_to_show))
        print "\nTop %d functions by number of rows looked at:" % num_to_show
        print "\n".join("{0:>7} {1}".format(num, string) for num, string in most_common([(x['sql_num_rows'], "{0}:{1}:L{2}".format(x['filename'], x['func_name'], x['func_start_lineno'])) for x in self.log_counter.filehits], num_to_show))
        print "\nTop %d lines by number of rows looked at:" % num_to_show
        print "\n".join("{0:>7} {1}".format(num, string) for num, string in most_common([(x['sql_num_rows'], "{0}:L{1}".format(x['filename'], x['lineno'])) for x in self.log_counter.filehits], num_to_show))

        print "\n{0:>12} queries in total".format(len(self.log_counter.queries))
        print "{0:>12} rows looked at in total".format(sum(x['num_rows'] or 0 for x in self.log_counter.queries))
        print "{0:>12} tables joined in total".format(sum(x['num_tables'] or 0 for x in self.log_counter.queries))
        print "{0:>12}s seconds spend in mysql".format(sum(x['duration'] or 0 for x in self.log_counter.queries))



