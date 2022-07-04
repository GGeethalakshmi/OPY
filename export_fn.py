import sys, re
from export_queries import *



def get_object(conn, object_type, object_name):
  # get object from database
  if object_type == 'JOB':
    desc = conn.fetch(query_describe_job, object_name = object_name)
  else:
    desc = conn.fetch(query_describe_object, object_type = object_type, object_name = object_name)
  #
  if len(desc) == 0:
    return
  return re.sub('\t', '    ', str(desc[0][0]).strip())  # replace tabs with 4 spaces



def get_object_comments(conn, object_name):
  lines = ['\n--']
  data = conn.fetch_assoc(query_table_comments, table_name = object_name)
  for row in data:
    lines.append('COMMENT ON TABLE {} IS \'{}\';'.format(object_name.lower(), (row.comments or '').replace('\'', '')))
  #
  data = conn.fetch_assoc(query_column_comments, table_name = object_name)
  if len(data) > 0:
    lines.append('--')
  for row in data:
    lines.append('COMMENT ON COLUMN {} IS \'{}\';'.format(row.column_name, (row.comments or '').replace('\'', '')))
  #
  return '\n'.join(lines)



def replace(subject, pattern, replacement, flags = 0):
  return re.compile(pattern, flags).sub(replacement, subject)



def get_lines(obj):
  lines = [s.rstrip() for s in obj.split('\n')]
  lines[0] = lines[0].lstrip()
  #
  return lines



def fix_simple_name(obj):
  obj = replace(obj, '("[A-Z0-9_$#]+")\.', '')
  obj = re.sub(r'"([A-Z0-9_$#]+)"', lambda x : x.group(1).lower(), obj)
  #
  return obj



def clean_table(lines):
  lines[0] = fix_simple_name(lines[0]) + ' ('
  lines[1] = lines[1].lstrip().lstrip('(').lstrip()  # fix fisrt column

  # throw away some distrators
  for (i, line) in enumerate(lines):
    if line.startswith('  STORAGE') or\
      line.startswith('  PCTINCREASE') or\
      line.startswith('  BUFFER_POOL') or\
      line.startswith('  USING'):
      lines[i] = ''
    else:
      lines[i] = lines[i].replace(' ENABLE', '').strip()
      lines[i] = lines[i].replace(' COLLATE "USING_NLS_COMP"', '')
      lines[i] = lines[i].replace(' DEFAULT COLLATION "USING_NLS_COMP"', '')
      lines[i] = lines[i].replace(' SEGMENT CREATION IMMEDIATE', '')
      lines[i] = lines[i].replace('(PARTITION', '(\n    PARTITION')
      lines[i] = lines[i].replace('" )', '"\n)')
      lines[i] = lines[i].replace('TIMESTAMP\' ', 'TIMESTAMP \'')

  # fix column alignment
  lines = '\n'.join(lines).split('\n')
  for (i, line) in enumerate(lines):
    # fic column name
    if line.startswith('"'):
      columns = lines[i].replace(' (', '(').strip().split(' ', 3)
      lines[i] = '    {:<30}  {:<16}{}'.format(
        fix_simple_name(columns[0]),
        columns[1].replace('NUMBER(*,0)', 'INTEGER') if len(columns) > 1 else '',
        fix_simple_name(' '.join(columns[2:])) if len(columns) > 2 else ''
      ).rstrip()
    #
    if line.startswith('PARTITION'):
      lines[i] = fix_simple_name(lines[i])
    #
    if line.startswith(')  PCTFREE'):
      lines[i] = ')'
    #
    if line.startswith(')  DEFAULT COLLATION "USING_NLS_COMP" PCTFREE'):
      lines[i] = ')'
    #
    if line.startswith('TABLESPACE') or\
      line.startswith('PCTFREE') or\
      line.startswith('NOCOMPRESS LOGGING'):
      lines[i] = ''
    #
    if line.startswith('CONSTRAINT'):
      lines[i] = '    --\n    ' + fix_simple_name(lines[i])
      lines[i] = lines[i].replace(' CHECK (', '\n        CHECK (')
      lines[i] = lines[i].replace(' PRIMARY KEY (', '\n        PRIMARY KEY (')
      lines[i] = lines[i].replace(' FOREIGN KEY (', '\n        FOREIGN KEY (')
      lines[i] = lines[i].replace(' UNIQUE (', '\n        UNIQUE (')
    #
    if line.startswith('REFERENCES'):
      lines[i] = '        ' + fix_simple_name(lines[i])
    #
    lines[i] = lines[i].replace(' DEFERRABLE', '\n        DEFERRABLE')

  # remove empty lines
  lines = list(filter(None, lines))
  lines[len(lines) - 1] += ';'
  return lines



def clean_view(lines):
  lines[0] = lines[0].replace(' DEFAULT COLLATION "USING_NLS_COMP"', '')
  lines[0] = lines[0].replace(' EDITIONABLE', '')
  lines[0] = replace(lines[0], r'\s*\([^)]+\)\s*AS', ' AS')                 # remove columns
  lines[0] = fix_simple_name(lines[0])
  lines[1] = lines[1].lstrip()
  lines[len(lines) - 1] += ';'
  #
  # @TODO: add comments (view + columns) -> might not execute if view is not valid
  #
  return lines



def clean_materialized_view(lines):
  lines[0] = replace(lines[0], r'\s*\([^)]+\)', '')                         # remove columns
  lines[0] = fix_simple_name(lines[0])
  lines[0] = lines[0].replace('CREATE', '-- DROP') + ';\n' + lines[0]

  # found query start
  splitter = 0
  for (i, line) in enumerate(lines):
    # search for line where real query starts
    if line.startswith('  AS '):
      lines[i] = line.replace('  AS ', 'AS\n')
      splitter = i
      break

    # throw away some distrators
    if line.startswith(' NOCOMPRESS') or\
      line.startswith('  DEFAULT COLLATION') or\
      line.startswith('  ORGANIZATION') or\
      line.startswith('  STORAGE') or\
      line.startswith('  TABLESPACE') or\
      line.startswith('  PCTINCREASE') or\
      line.startswith('  BUFFER_POOL') or\
      line.startswith('  USING'):
      lines[i] = ''
    else:
      lines[i] = lines[i].lstrip()

  # remove empty lines
  lines[len(lines) - 1] += ';'
  lines = list(filter(None, lines[0:splitter])) + lines[splitter:]
  #
  return lines



def clean_package(lines):
  lines = clean_procedure(lines)

  # remove body
  for (i, line) in enumerate(lines):
    if line.replace(' EDITIONABLE', '').startswith('CREATE OR REPLACE PACKAGE BODY'):
      lines = lines[0:i]
      lines[len(lines) - 1] += '\n/'
      break
  #
  return lines



def clean_package_body(lines):
  return clean_procedure(lines)



def clean_procedure(lines):
  lines[0] = fix_simple_name(lines[0])
  lines[0] = lines[0].replace(' EDITIONABLE', '')
  lines[len(lines) - 1] += '\n/'
  return lines



def clean_function(lines):
  return clean_procedure(lines)



def clean_sequence(lines):
  lines[0] = lines[0].replace(' MAXVALUE 9999999999999999999999999999', '')
  lines[0] = lines[0].replace(' INCREMENT BY 1', '')
  lines[0] = lines[0].replace(' NOORDER', '')
  lines[0] = lines[0].replace(' NOCYCLE', '')
  lines[0] = lines[0].replace(' NOKEEP', '')
  lines[0] = lines[0].replace(' NOSCALE', '')
  lines[0] = lines[0].replace(' GLOBAL', '')
  lines[0] = lines[0].replace(' GLOBAL', '')
  #
  lines[0] = fix_simple_name(lines[0])
  lines[0] = replace(lines[0], '\s+', ' ').strip() + ';'
  #
  lines[0] = lines[0].replace(' MINVALUE', '\n    MINVALUE')
  lines[0] = lines[0].replace(' START', '\n    START')
  lines[0] = lines[0].replace(' CACHE', '\n    CACHE')
  #
  lines = '\n'.join(lines).split('\n')
  lines[0] = lines[0].replace('CREATE', '-- DROP') + ';\n' + lines[0]
  #
  return lines



def clean_trigger(lines):
  lines[0] = fix_simple_name(lines[0])
  lines[0] = lines[0].replace(' EDITIONABLE', '')

  # fix enable/disable trigger
  found_slash = False
  for (i, line) in enumerate(lines):
    if line.startswith('ALTER TRIGGER'):
      lines[i] = replace(line, 'ALTER TRIGGER "[^"]+"."[^"]+" ENABLE', '');
      if '" DISABLE' in line:
        lines[i] = fix_simple_name(line.replace(' DISABLE', ' DISABLE;'));
        lines[i - 1] = '/\n';
        found_slash = True

  # fix missing slash
  if not found_slash:
    lines[len(lines) - 2] = '/';
  #
  return lines



def clean_index(lines):
  for (i, line) in enumerate(lines):
    # throw away some distrators
    if line.startswith('  STORAGE') or\
      line.startswith('  PCTFREE') or\
      line.startswith('  PCTINCREASE') or\
      line.startswith('  BUFFER_POOL'):
      lines[i] = ''
    else:
      lines[i] = lines[i].lstrip()
      lines[i] = lines[i].replace('TABLESPACE', '    COMPUTE STATISTICS\n    TABLESPACE')
  #
  lines[0] = fix_simple_name(lines[0]).replace(' ON ', '\n    ON ')
  lines = list(filter(None, lines))
  lines[len(lines) - 1] += ';'
  #
  return lines



