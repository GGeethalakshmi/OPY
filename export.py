# coding: utf-8
import sys, os, argparse, pickle, timeit, glob, csv
from oracle_wrapper import Oracle
from export_fn import *

# args
parser = argparse.ArgumentParser()
parser.add_argument('target',           help = 'Target folder (Git root)')
parser.add_argument('-n', '--name',     help = 'Connection name')
parser.add_argument('-t', '--type',     help = 'Filter specific object type', default = '')
parser.add_argument('-r', '--recent',   help = 'Filter objects compiled since SYSDATE - $recent')
parser.add_argument('-a', '--app',      help = 'APEX application')
parser.add_argument('-p', '--page',     help = 'APEX page')
parser.add_argument('-c', '--csv',      help = '', nargs = '?', default = False, const = True)
parser.add_argument('-v', '--verbose',  help = '', nargs = '?', default = False, const = True)
parser.add_argument('-d', '--debug',    help = '', nargs = '?', default = False, const = True)
#
args = vars(parser.parse_args())

# check args
if args['debug']:
  print('ARGS:\n-----')
  for (key, value) in args.items():
    if not (key in ('pwd', 'wallet_pwd')):
      print('{:>8} = {}'.format(key, value))
  print('')

# current dir
root = os.path.dirname(os.path.realpath(__file__))
conn_dir = '/conn'



# connect to database
start = timeit.default_timer()
db_conf = args['target'] + 'python/db.conf'
if args['name']:
  db_conf = '{}{}/{}.conf'.format(root, conn_dir, args['name'])
#
print('CONNECTING:\n-----------\n  {}\n'.format(db_conf))
conn = None
with open(db_conf, 'rb') as f:
  conn = Oracle(pickle.load(f))



#
# PREVIEW OBJECTS
#
if args['recent'] == None or int(args['recent']) > 0:
  print('OBJECTS PREVIEW:\n----------------')
  data_objects = conn.fetch_assoc(query_objects, object_type = args['type'].upper(), recent = args['recent'])
  summary = {}
  for row in data_objects:
    if not (row.object_type) in summary:
      summary[row.object_type] = 0
    summary[row.object_type] += 1
  #
  all_objects = conn.fetch_assoc(query_all_objects)
  for row in all_objects:
    print('{:>20} | {:>4} | {:>4}'.format(row.object_type, summary.get(row.object_type, ''), row.count_))
  print('                          ^')
  print('    CONSTRAINTS:\n    ------------')
  data_constraints = conn.fetch_assoc(query_constraints)
  for row in data_constraints:
    print('{:>8} | {}'.format(row.constraint_type, row.count_))
  print()

# target folders by object types
target = args['target'] + '/database/'
folders = {
  'TABLE'             : target + 'tables/',
  'VIEW'              : target + 'views/',
  'MATERIALIZED VIEW' : target + 'mviews/',
  'TRIGGER'           : target + 'triggers/',
  'INDEX'             : target + 'indexes/',
  'SEQUENCE'          : target + 'sequences/',
  'PROCEDURE'         : target + 'procedures/',
  'FUNCTION'          : target + 'functions/',
  'PACKAGE'           : target + 'packages/',
  'PACKAGE BODY'      : target + 'packages/',
  'JOB'               : target + 'jobs/',
  'DATA'              : target + 'data/',
  'GRANT'             : target + 'grants/',
  'APEX'              : target + 'apex/',
}

#
# EXPORT OBJECTS
#
if args['recent'] == None or int(args['recent']) > 0:
  print('EXPORTING:', '\n----------' if args['verbose'] else '')
  for (i, row) in enumerate(data_objects):
    object_type, object_name = row.object_type, row.object_name

    # make sure we have target folders ready
    folder = folders[object_type]
    if not (os.path.isdir(folder)):
      os.makedirs(folder)
    #
    extra = ''
    if object_type == 'PACKAGE':
      extra = '.spec'
    #
    obj   = get_object(conn, object_type, object_name)
    file  = '{}{}{}.sql'.format(folder, object_name.lower(), extra)
    #
    if args['verbose']:
      print('{:>20} | {:<30} {:>8}'.format(object_type, object_name, len(obj)))
    else:
      perc        = (i + 1) / len(data_objects)
      dots        = int(70 * perc)
      sys.stdout.write('\r' + ('.' * dots) + ' ' + str(int(perc * 100)) + '%')
      sys.stdout.flush()
    #
    lines = get_lines(obj)
    lines = getattr(sys.modules[__name__], 'clean_' + object_type.replace(' ', '_').lower())(lines)
    obj   = '\n'.join(lines) + '\n\n'

    # write object to file
    with open(file, 'w', encoding = 'utf-8') as h:
      h.write(obj)
  print()

#
# EXPORT DATA
#
if args['csv']:
  files = [os.path.splitext(os.path.basename(file))[0] for file in glob.glob(folders['DATA'] + '*.csv')]
  ignore_columns = ['updated_at', 'updated_by', 'created_at', 'created_by', 'calculated_at']
  #
  print('\nEXPORT TABLES DATA:', len(files))
  print('-------------------')
  #
  for table_name in sorted(files):
    try:
      table_exists = conn.fetch('SELECT 1 FROM {} WHERE ROWNUM = 1'.format(table_name))[0][0]
    except:
      continue
    #
    file        = '{}{}.csv'.format(folders['DATA'], table_name)
    csv_file    = open(file, 'w')
    writer      = csv.writer(csv_file, delimiter = ';', lineterminator = '\n', quoting = csv.QUOTE_NONNUMERIC)
    columns     = [col for col in conn.cols if not (col in ignore_columns)]
    order_by    = ', '.join([str(i) for i in range(1, min(len(columns), 5) + 1)])
    data        = conn.fetch('SELECT {} FROM {} ORDER BY {}'.format(', '.join(columns), table_name, order_by))
    #
    writer.writerow(conn.cols)  # headers
    print('  {:30} {:>8}'.format(table_name, len(data)))
    for row in data:
      writer.writerow(row)
    csv_file.close()

print('\nTIME:', round(timeit.default_timer() - start, 2))
print('\n')


