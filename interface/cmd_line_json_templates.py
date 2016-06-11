

def ls(tpl, tag='result'):
    return "{.section %s}{.repeated section @}%s{.end}{.end}" % (tag, tpl)

#------------------------------------------------------------------------------ 

tpl_status = "{.section status}{@}{.end}"
tpl_result = ls("{@}\n")
tpl_message = "{.section message}{@}{.end}"
tpl_errors = ls("{@}\n", tag="errors")
tpl_execution = "{.section execution}: {@} sec.{.end}"
tpl_4_items = """{0}{1}
{2}{3}
"""
tpl_5_items = """{0}{1}
{2}{3}{4}
"""

#------------------------------------------------------------------------------ 

TPL_JSON = "{@}"

#------------------------------------------------------------------------------ 

TPL_RAW = tpl_5_items.format(
    tpl_status, tpl_execution, tpl_result, tpl_message, tpl_errors)

#------------------------------------------------------------------------------ 

TPL_BACKUPS_LIST = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{id} {type} {size} {path} {.section versions}{.repeated section @}[{version}: {size} (#{blocks})]{.end}{.end}\n"),
    tpl_errors)

TPL_BACKUPS_LIST_IDS = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{backupid} {size} {path}\n"),
    tpl_errors)

TPL_BACKUPS_RUNNING_LIST = tpl_5_items.format(
    tpl_status,
    tpl_execution,
    ls("{backup_id} from {source_path} of total {total_size}, currently {bytes_processed} bytes processed, ready by {progress}%\n"), 
    tpl_message,
    tpl_errors)

TPL_BACKUPS_TASKS_LIST = tpl_5_items.format(
    tpl_status,
    tpl_execution,
    ls("{id}: {path_id} from {local_path} created at {created}\n"),
    tpl_message,
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_RESTORES_RUNNING_LIST = tpl_5_items.format(
    tpl_status,
    tpl_execution,
    ls("{backup_id}, currently {bytes_processed} bytes processed\n"),
    tpl_message,
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_OPTIONS_LIST_KEY_TYPE_VALUE = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{key} ({type}) : {value}\n"),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_OPTION_MODIFIED = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{key} ({type}) : {value}{.section old_value}, previous : {@}{.or}{.end}\n"),
    tpl_errors)

TPL_OPTION_SINGLE = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{key} ({type}) : {value}{.section old_value}, previous : {@}{.or}{.end}\n"),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_SUPPLIERS = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{position}: {idurl}, since {connected}, keeps {numfiles} files, {status}\n"),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_CUSTOMERS = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("{position}: {idurl}, {status}\n"),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_STORAGE = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("""{.section consumed}consumed:
    suppliers: {suppliers_num}
    needed: {needed} ({needed_str})
    used: {used} ({used_str}) {used_percent}
    available: {available} ({available_str})
    donated from each supplier: {needed_per_supplier} ({needed_per_supplier_str})
    used on each supplier: {used_per_supplier} ({used_per_supplier_str})
    available on every supplier: {available_per_supplier} ({available_per_supplier_str})
{.end}{.section donated}donated:
    customers: {customers_num} 
    donated: {donated} ({donated_str})
    allocated: {consumed} ({consumed_str}) {consumed_percent}
    uploaded: {used} ({used_str}) {used_percent}
{.section customers}{.repeated section @}      {idurl} uploaded {real_str} from {consumed_str}\n{.end}{.end}{.end}{.section local}local:
    disk size: {disktotal} ({disktotal_str})
    disk free: {diskfree} ({diskfree_str}) {diskfree_percent}
    disk consumed: {total} ({total_str}) {total_percent}
      buffered files: {backups} ({backups_str}) 
      temporary files: {temp} ({temp_str})
      customers files: {customers} ({customers_str})
{.end}"""),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_AUTOMATS = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls('{index}: {name}({state}) {.section timers}   timers: {@}{.end}\n'),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_SERVICES = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls('{index}: {name}({state}) {enabled_label}, {num_depends} depends\n'),
    tpl_errors)

TPL_SERVICE_INFO = tpl_4_items.format(
    tpl_status,
    tpl_execution,
    ls("""ID: {index}
name: {name}
state: {state}
enabled: {enabled}
dependent on: {.section depends}{.repeated section @}{@}{.alternates with}, {.end}{.end}
config path: /config/{config_path}
"""),
    tpl_errors)

#------------------------------------------------------------------------------ 

TPL_FRIEND_LOOKUP = """{.section result}
friend lookup:
    {result}
    {nickname}
    {position}
    {idurl}
{.end}"""

TPL_FRIEND_LOOKUP_REPEATED_SECTION = """{.section result}
friends:
{.repeated section @}
    {idurl} : {nickname}
{.end}
{.end}"""

TPL_MESSAGE_SENDING = """{.section result}
    {@}
{.end}
{.section error}
    error: {@}
{.end}
    recipient: {.section recipient}{@}{.end}
"""
