django-sql-inspector allows deep measurment and analysis of the MySQL calls in your project

It allows one to write a management command that interacts with your project
using Django's Test Client. As SQL calls are made, it prints out what is
causing those SQL call (what files and functions are responsible, all the way
up the stack) and information about the query (type, duration, number of tables
used).

It currently only works with MySQL.

# Motivation and design philosophy

I created this library when needing to measure and optimize an existing Django application. It was a large application, and I wanted to optimize a particular popular 'flow'. There were many layers, function 1 called function 2 called function 3 which did an SQL query. I wanted to be able to see what functions were responsible for what SQL. I wanted to be able to measure, in a reproducible way, the amount of SQL being called, so I could reduce it and measure the improvements.

# Installation

    pip install django-sql-inspector

# Usage

Create a [custom django mangement command](https://docs.djangoproject.com/en/dev/howto/custom-management-commands/) in the usual way. I like to create a command ``measure_sql_performance.py``.

However, rather than subclassing ``django.core.management.base.BaseCommand``, you must subclass ``sql_inspector.MeasureSQLCommand``, and rather than using ``handle`` as the entry point, you must use ``inner_handle``.

An instance of [Django's Test Client](https://docs.djangoproject.com/en/dev/topics/testing/overview/#module-django.test.client) (i.e. simple web browser) will be created and is available as ``self.client``.

## Example

A simple example might look like this:

    from sql_inspector import MeasureSQLCommand
    
    class Command(MeasureSQLCommand):
    
        def inner_handle(self, *args, **options):
            self.client.get("/")
            self.client.get("/polls/")

This just goes to ``/`` and then ``/polls/``. Since this is full python, you can parse the HTML, follow links, submit forms, etc. to accurately simulate what a user would do.

# Output

If you run this management command against the django example polls app (you can find a copy of the code [here](https://github.com/shimon/djangotutorial), you'll have to change the database from sqlite3 to mysql), you'll get this output:


                             index @ /tmp/djangoexample/mysite/polls/views.py:L13    (function starts at L10   )
                      inner_handle @ /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:L7     (function starts at L5    )
    Query used     1 tables in     0.00 sec and needed to look at     1 rows
    Query used     1 tables: polls_poll
    SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER BY `polls_poll`.`pub_date` DESC LIMIT 5 ()

    Aggregate statistics:

    Top 20 files:
        1 /tmp/djangoexample/mysite/polls/views.py
        1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py

    Top 20 lines:
        1 /tmp/djangoexample/mysite/polls/views.py:L13
        1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:L7

    Top 20 functions:
        1 inner_handle in /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py (L5)
        1 index in /tmp/djangoexample/mysite/polls/views.py (L10)

    Top SQL statment types:
        1 SELECT

    Top 20 queries by number of rows looked at:
          1 SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER B ()

    Top 10 queries by number of table joins:
          1 SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER B ()

    Top 10 queries by SQL duration:
        0.0003 SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER B ()

    Top 20 files by number of rows looked at:
          1 /tmp/djangoexample/mysite/polls/views.py
          1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py

    Top 20 functions by number of rows looked at:
          1 /tmp/djangoexample/mysite/polls/views.py:index:L10
          1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:inner_handle:L5

    Top 20 lines by number of rows looked at:
          1 /tmp/djangoexample/mysite/polls/views.py:L13
          1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:L7

               1 queries in total
               1 rows looked at in total
               1 tables joined in total
    0.000270128250122s seconds spend in mysql


## Output Explaination

It prints out details for each SQL query that is executed and then a summary of queries and files.

### For each SQL query

This is what is printed out for one SQL query:

                             index @ /tmp/djangoexample/mysite/polls/views.py:L13    (function starts at L10   )
                      inner_handle @ /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:L7     (function starts at L5    )

The stack trace of what caused the SQL call, one line per function call. The topmost line is 'closer' to the SQL, and the bottommost line will probably be your management command.

Each line is of the format: ``$FUNCTION_NAME @ $FILENAME:L$LINENUMBER  (function starts at L$LINE_OF_FUNCTION_DEF)``. The ``$LINENUMBER`` is the line at which that called the SQL, ``$LINE_OF_FUNCTION_DEF`` is the line number at which that function started. Some files will have many functions with the same name (e.g. ``models.py`` will probably have many ``__unicode__`` functions).

    Query used     1 tables in     0.00 sec and needed to look at     1 rows

Summary of query, how many tables were joined, how long the query took to execute, and how many rows MySQL's ``EXPLAIN`` says it should have to look at. Large number of rows mean you may need more indexes.

    Query used     1 tables: polls_poll

Number of, and what tables were used in this query. Catch over eager table joins here

    SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER BY `polls_poll`.`pub_date` DESC LIMIT 5 ()

The SQL itself, as a prepared query. The ``()`` at the end tells us there was no parameters.

### Summary statistics

    Aggregate statistics:

    Top 20 files:
        1 /tmp/djangoexample/mysite/polls/views.py
        1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py

What files are responsible for the most amount of SQL queries?

    Top 20 lines:
        1 /tmp/djangoexample/mysite/polls/views.py:L13
        1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:L7

What individual lines are responsbile for the most amount of SQL queries?

    Top 20 functions:
        1 inner_handle in /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py (L5)
        1 index in /tmp/djangoexample/mysite/polls/views.py (L10)

What functions are responsible for the most amount of SQL queries?

    Top SQL statment types:
        1 SELECT

How much of each query type (``SELECT``/``UPDATE``/etc.) in total was there?

    Top 20 queries by number of rows looked at:
          1 SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER B ()

What SQL queries are looking at the most amount of rows? Investigate what queries might need a SQL indexes.

    Top 10 queries by number of table joins:
          1 SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER B ()

What SQL queries are using the most amount of SQL table joins

    Top 10 queries by SQL duration:
        0.0003 SELECT `polls_poll`.`id`, `polls_poll`.`question`, `polls_poll`.`pub_date` FROM `polls_poll` ORDER B ()

What SQL queries are taking the longest?

    Top 20 files by number of rows looked at:
          1 /tmp/djangoexample/mysite/polls/views.py
          1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py

What files are responsible for looking at many rows?

    Top 20 functions by number of rows looked at:
          1 /tmp/djangoexample/mysite/polls/views.py:index:L10
          1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:inner_handle:L5

What functions are responsible for looking at many rows?

    Top 20 lines by number of rows looked at:
          1 /tmp/djangoexample/mysite/polls/views.py:L13
          1 /tmp/djangoexample/mysite/polls/management/commands/measure_sql_performance.py:L7

What lines are responsible for looking at many rows?

               1 queries in total

Total number of queries

               1 rows looked at in total

Total number of rows

               1 tables joined in total

Total number of tables joined/looked at.

    0.000270128250122s seconds spend in mysql

Total amount of time spent doing SQL queries



# Comparison with other tools

## Django Debug Toolbar

[Django Debug Toolbar](https://github.com/django-debug-toolbar/django-debug-toolbar) is a great tool that can also measure what SQL is used and show output on what tables/indexes are used. However it works on a per-page basis, not per-'user flow', it displays results in the web browser, so you can't analyse it in a file, it will not group queries based on file or functions.


# Copyright & Licence

Copyright 2013, Rory McCann <rory@technomancy.org>. Released under GNU General Public Licence, version 3, or (at your option) any later version. See the file LICENCE for the actual GNU GPLv3+ licence.


[![Bitdeli Badge](https://d2weczhvl823v0.cloudfront.net/rory/django-sql-inspector/trend.png)](https://bitdeli.com/free "Bitdeli Badge")

