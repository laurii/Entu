# maintenance.py

# - Get chunk of newly created or deleted properties
# - Revaluate formulas
#   - For new formula property calculate it's value
#   - For any parent entity recalculate formulas affected by property
#   - For any child entity recalculate formulas affected by property
#   - For "self" entity recalculate formulas affected by property
#   - For back-referencing entity recalculate formulas affected by property
# - Populate value_display
# - Get entities for affected properties
# - Reindex entity_info

from datetime import datetime
import argparse
import yaml
import json
import time

from etask import *


parser = argparse.ArgumentParser()
parser.add_argument('--database-host',     required = True)
parser.add_argument('--database-name',     required = True)
parser.add_argument('--database-user',     required = True)
parser.add_argument('--database-password', required = True)
parser.add_argument('--customergroup',     required = False, default = '0')
parser.add_argument('-v', '--verbose',     action = 'count')
args = parser.parse_args()

# Set verbosity level
verbose = 0
if args.verbose:
    verbose = args.verbose

timestamp_file = 'maintenance.yaml'
last_checked = {}
try:
    with open(timestamp_file, 'r+') as f:
        last_checked = yaml.load(f.read())
except IOError as e:
    print "\n\n%s No timestamp file '%s'." % (datetime.now(), timestamp_file)

task = ETask(args)

i = 0
sleepfactor = 0.025
mov_ave = 0.99
chunk_size = 100

if verbose > 3:
    profiling_sum = {'displayfields': 0.00
                   , 'displayproperties': 0.00
                   , 'INSERT': 0.00
    }

while True:
    d_start = datetime.now()
    i = last_checked.setdefault('_metrics', {}).setdefault('run_id', 0)

    print "\n\n%s Run %s" % (d_start, i)

    task.reload_customers()
    # print json.dumps(task.customers, sort_keys=True, indent=4, separators=(',', ': '))

    for customer_row in task.customers.values():
        # print json.dumps(customers, sort_keys=True, indent=4, separators=(',', ': '))
        db = torndb.Connection(
            host     = customer_row.get('database-host')[0],
            database = customer_row.get('database-name')[0],
            user     = customer_row.get('database-user')[0],
            password = customer_row.get('database-password')[0],
        )

        last_checked.setdefault(customer_row.get('domain')[0], {}).setdefault('last_id', 0)
        last_checked.setdefault(customer_row.get('domain')[0], {}).setdefault('latest_checked', '1001-01-01 00:00:00')
        last_checked.setdefault(customer_row.get('domain')[0], {}).setdefault('property_status', '')
        last_checked.setdefault(customer_row.get('domain')[0], {}).setdefault('entity_status', '')
        last_checked.setdefault('_metrics', {}).setdefault('properties_checked', 0.0000)
        last_checked.setdefault('_metrics', {}).setdefault('entities_checked', 0.0000)
        last_checked.setdefault('_metrics', {}).setdefault('time_spent', 0.0000)

        customer_started_at = datetime.now()
        if verbose > 0: print "\n%s Starting for --== %s ==--." % (datetime.now(), customer_row.get('domain')[0])

        check_time = last_checked[customer_row.get('domain')[0]]['latest_checked']
        if verbose > 1: print "%s Looking for properties fresher than %s." % (datetime.now()-customer_started_at, check_time)
        # print EQuery().fresh_properties(chunk_size, check_time, False)
        property_table = db.query(EQuery().fresh_properties(chunk_size, check_time, False))
        properties_to_check = len(property_table)
        if properties_to_check == 0:
            continue
        if verbose > 2: print "%s Got %s properties." % (datetime.now()-customer_started_at, properties_to_check)
        # If chunk size of rows returned, then reload query with next second properties only.
        if properties_to_check == chunk_size:
            first_second = property_table[0].o_date
            last_second = property_table[chunk_size-1].o_date
            if verbose > 2: print "%s Reloading properties with timestamp between %s and %s inclusive." % (datetime.now()-customer_started_at, first_second, last_second)
            try:
                # print EQuery().fresh_properties(chunk_size, first_second, last_second)
                property_table = db.query(EQuery().fresh_properties(chunk_size, first_second, last_second))
            except Exception as e:
                print EQuery().fresh_properties(chunk_size, first_second, last_second)
                print "\n%s: failed for %s." % (datetime.now()-customer_started_at, customer_row.get('database-name')[0])
                raise e

            properties_to_check = len(property_table)
            if verbose > 2: print "%s Got %s properties with timestamp between %s and %s inclusive." % (datetime.now()-customer_started_at, properties_to_check, first_second, last_second)
            last_checked[customer_row.get('domain')[0]]['property_status'] = 'Catching up with properties'
        else:
            last_checked[customer_row.get('domain')[0]]['property_status'] = 'In real time'

        # Property revaluation
        if verbose > 0: print "%s Checking %i properties." % (datetime.now()-customer_started_at, properties_to_check)
        for property_row in property_table:
            task.check_my_formulas(db, property_row)
            task.check_my_value_display(db, property_row)
            last_checked[customer_row.get('domain')[0]]['last_id'] = property_row.id
            last_checked[customer_row.get('domain')[0]]['latest_checked'] = str(property_row.o_date)
        if verbose > 2: print "%s Property check finished." % (datetime.now()-customer_started_at)

        # Entity info refresh
        entities_to_index = []
        if last_checked[customer_row.get('domain')[0]]['property_status'] == 'In real time':
            if verbose > 2: print "%s Looking for entity id's." % (datetime.now()-customer_started_at)
            if last_checked[customer_row.get('domain')[0]]['entity_status'] == 'In real time':
                for property_row in property_table:
                    entities_to_index.append({'id': property_row.entity_id})
            else:
                entities_to_index = db.query("SELECT id FROM entity WHERE is_deleted = 0")
                # print entities_to_index
            if verbose > 0: print "%s There are %i unique entities to reindex." % (datetime.now()-customer_started_at, len(entities_to_index))
            for entity in entities_to_index:
                profiling = task.refresh_entity_info(db, entity['id'], customer_row.get('language-ref'))
                if verbose > 3:
                    profiling_sum['displayfields'] = profiling_sum['displayfields'] + profiling['displayfields']
                    profiling_sum['displayproperties'] = profiling_sum['displayproperties'] + profiling['displayproperties']
                    profiling_sum['INSERT'] = profiling_sum['INSERT'] + profiling['INSERT']
            last_checked[customer_row.get('domain')[0]]['entity_status'] = 'In real time'
            if verbose > 2: print "%s %i entities reindexed." % (datetime.now()-customer_started_at, len(entities_to_index))
            if verbose > 3: print json.dumps(profiling_sum, indent=4, separators=(',', ': '))

        customer_finished_at = datetime.now()
        customer_time_spent = customer_finished_at - customer_started_at

        last_checked['_metrics']['properties_checked'] = mov_ave * last_checked['_metrics']['properties_checked'] + properties_to_check
        last_checked['_metrics']['entities_checked'] = mov_ave * last_checked['_metrics']['entities_checked'] + len(entities_to_index)
        last_checked['_metrics']['time_spent'] = mov_ave * last_checked['_metrics']['time_spent'] + customer_time_spent.microseconds + (customer_time_spent.seconds + customer_time_spent.days * 86400) * 1000000

        with open(timestamp_file, 'w+') as f:
            f.write(yaml.safe_dump(last_checked, default_flow_style=False, allow_unicode=True))

    last_checked['_metrics']['run_id'] = i + 1
    with open(timestamp_file, 'w+') as f:
        f.write(yaml.safe_dump(last_checked, default_flow_style=False, allow_unicode=True))

    d_stop = datetime.now()
    time_delta = d_stop - d_start
    time_spent_sec = 0.000001*time_delta.microseconds + time_delta.seconds + time_delta.days*86400
    sleep = min(time_spent_sec * sleepfactor + sleepfactor * 1, sleepfactor * 20)
    print "%s (%2.2f seconds). Now sleeping for %2.2f seconds." % (d_stop, time_spent_sec, sleep)
    print "Moving average (%1.2f) properties/second: %3.2f; entities/second: %3.2f." % (
        mov_ave,
        1000000.00*last_checked['_metrics']['properties_checked']/last_checked['_metrics']['time_spent'],
        1000000.00*last_checked['_metrics']['entities_checked']/last_checked['_metrics']['time_spent'])
    time.sleep(sleep)
    if verbose > 4: raw_input('Press enter')
