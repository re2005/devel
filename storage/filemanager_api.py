#!/usr/bin/python
#filemanager_api.py
#
# Copyright (C) 2008-2016 Veselin Penev, http://bitdust.io
#
# This file (filemanager_api.py) is part of BitDust Software.
#
# BitDust is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BitDust Software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with BitDust Software.  If not, see <http://www.gnu.org/licenses/>.
#
# Please contact us if you have any questions at bitdust.io@gmail.com
#
#
#
#

"""
.. module:: filemanager_api

"""

#------------------------------------------------------------------------------ 

import os
import sys
import time
import pprint

from logs import lg

from system import bpio

from lib import packetid
from lib import misc

from main import settings

from services import driver

from transport import packet_in
from transport import packet_out

from storage import backup_fs
from storage import backup_control
from storage import backup_monitor
from storage import restore_monitor

from web import control 


#------------------------------------------------------------------------------ 

def process(json_request):
    lg.out(20, 'filemanager_api.process %s' % json_request)
    if not driver.is_started('service_backups'):
        return { 'result': {
            "success": False,
            "error": "network [service_backups] is not started: %s" % (
               driver.services().get('service_backups', '!!! not found !!!')) }}
    mode = ''
    result = {}
    try:
        if isinstance(json_request, str) or isinstance(json_request, unicode):
            import json
            json_request = json.loads(json_request)
        mode = json_request['params']['mode']
        if mode == 'config':
            result = _config(json_request['params'])
        elif mode == 'stats':
            result = _stats(json_request['params'])
        elif mode == 'list':
            result = _list(json_request['params'])
        elif mode == 'listlocal':
            result = _list_local(json_request['params'])
        elif mode == 'listall':
            result = _list_all(json_request['params'])
        elif mode == 'upload':
            result = _upload(json_request['params'])
        elif mode == 'delete':
            result = _delete(json_request['params'])
        elif mode == 'deleteversion':
            result = _delete_version(json_request['params'])
        elif mode == 'download':
            result = _download(json_request['params'])
        elif mode == 'tasks':
            result = _list_active_tasks(json_request['params'])
        elif mode == 'transfers':
            result = _list_packet_transfers(json_request['params'])
        elif mode == 'debuginfo':
            result = _debuginfo(json_request['params'])
        else:
            result = {"result":{"success": False, 
                                "error": 'filemanager method %s not found' % mode }}
    except Exception as exc:
        lg.exc()
        descr = str(sys.exc_info()[0].__name__) + ': ' + str(sys.exc_info()[1])
        result = { "result": {"success": False,
                              "error": descr}} 
    # lg.out(4, '    ERROR unknown mode: %s' % mode)
    lg.out(20, '    %s' % pprint.pformat(result))
    return result

#------------------------------------------------------------------------------ 

def _config(params):
    result = []
    homepath = bpio.portablePath(os.path.expanduser('~'))
    if bpio.Windows():
        # set "c:" as a starting point when pick files for Windows
        # probably should be MyDocuments folder or something else,
        # but lets take that for now
        homepath = homepath[:2]
    result.append({'key': 'homepath', 
                   'value': homepath})
    return { 'result': result, }

def _stats(params):
    from contacts import contactsdb
    from p2p import contact_status
    from lib import diskspace
    result = {}
    result['suppliers'] = contactsdb.num_suppliers()
    result['max_suppliers'] = settings.getSuppliersNumberDesired()
    result['online_suppliers'] = contact_status.countOnlineAmong(contactsdb.suppliers())
    result['customers'] = contactsdb.num_customers()
    result['bytes_donated'] = settings.getDonatedBytes()
    result['value_donated'] = diskspace.MakeStringFromBytes(settings.getDonatedBytes())
    result['bytes_needed'] = settings.getNeededBytes()
    result['value_needed'] = diskspace.MakeStringFromBytes(settings.getNeededBytes())
    result['bytes_used_total'] = backup_fs.sizebackups()
    result['value_used_total'] = diskspace.MakeStringFromBytes(backup_fs.sizebackups())
    result['bytes_used_supplier'] = 0 if (contactsdb.num_suppliers() == 0) else (int(backup_fs.sizebackups() / contactsdb.num_suppliers()))
    result['bytes_indexed'] = backup_fs.sizefiles() + backup_fs.sizefolders()
    result['files_count'] = backup_fs.numberfiles()  
    result['folders_count'] = backup_fs.numberfolders()  
    result['items_count'] = backup_fs.counter() 
    result['timestamp'] = time.time()
    return { 'result': result, }

def _list(params):
    result = []
    path = params['path']
    if bpio.Linux() or bpio.Mac():
        path = '/' + path.lstrip('/')
    lst = backup_fs.ListByPathAdvanced(path)
    if not isinstance(lst, list):
        lg.warn('backup_fs.ListByPathAdvanced returned: %s' % lst)
        return { "result": [], }
    for item in lst:
        if item[2] == 'index':
            continue
        result.append({
            "type": item[0], 
            "name": item[1],
            "id": item[2],
            "rights": "",
            "size": item[3],
            "date": item[4],
            "dirpath": item[5],
            "has_childs": item[6],
            "content": '1' if item[7] else '',
            "versions": item[8],
        })
    return { 'result': result, }


def _list_all(params):
    result = []
    lst = backup_fs.ListAllBackupIDsAdvanced()
    for item in lst:
        if item[2] == 'index':
            continue
        result.append({
            "type": item[0], 
            "name": item[1],
            "id": item[2],
            "rights": "",
            "size": item[3],
            "date": item[4],
            "dirpath": item[5],
            "has_childs": item[6],
            "content": '1' if item[7] else '',
            "versions": item[8],
        })
    return { 'result': result, }


def _list_local(params):
    result = []
    path = params['path']
    if bpio.Linux() or bpio.Mac():
        path = '/' + path.lstrip('/')
    path = bpio.portablePath(path)
    only_folders = params['onlyFolders']
    if ( path == '' or path == '/' ) and bpio.Windows():
        for itemname in bpio.listLocalDrivesWindows():
            result.append({
                "name": itemname.rstrip('\\').rstrip('/').lower(),
                "rights": "drwxr-xr-x",
                "size": "",
                "date": "",
                "type": "dir",
                "dirpath": path,
            })
    else:
        if bpio.Windows() and len(path) == 2 and path[1] == ':':
            path += '/'
        apath = path
        for itemname in bpio.list_dir_safe(apath):
            itempath = os.path.join(apath, itemname)
            if only_folders and not os.path.isdir(itempath):
                continue
            result.append({
                "name": itemname,
                "rights": "drwxr-xr-x",
                "size": str(os.path.getsize(itempath)),
                "date": str(os.path.getmtime(itempath)),
                "type": "dir" if os.path.isdir(itempath) else "file", 
                "dirpath": apath,
            })
    return { 'result': result, }
  

def _upload(params):
    path = params['path']
    if bpio.Linux() or bpio.Mac():
        path = '/' + (path.lstrip('/'))
    localPath = unicode(path)
    if not bpio.pathExist(localPath):
        return { 'result': { "success": False, "error": 'local path %s was not found' % path } } 
    result = []
    pathID = backup_fs.ToID(localPath)
    if pathID is None:
        if bpio.pathIsDir(localPath):
            pathID, iter, iterID = backup_fs.AddDir(localPath, True)
            result.append('new folder was added: %s' % localPath)
        else:
            pathID, iter, iterID = backup_fs.AddFile(localPath, True)
            result.append('new file was added: %s' % localPath)
    backup_control.StartSingle(pathID, localPath)
    backup_fs.Calculate()
    backup_control.Save()
    control.request_update([('pathID', pathID),])
    result.append('backup started: %s' % pathID)
    return { 'result': result, }


def _download(params):
    # localName = params['name']
    backupID = params['backupid']
    destpath = params['dest_path']
    if bpio.Linux() or bpio.Mac():
        destpath = '/' + destpath.lstrip('/')
    restorePath = bpio.portablePath(destpath)
    # overwrite = params['overwrite']
    if not packetid.Valid(backupID):
        return { 'result': { "success": False, "error": "path %s is not valid" % backupID} }
    pathID, version = packetid.SplitBackupID(backupID)
    if not pathID:
        return { 'result': { "success": False, "error": "path %s is not valid" % backupID} }
    if backup_control.IsBackupInProcess(backupID):
        return { 'result': { "success": True, "error": None } }
    if backup_control.HasTask(pathID):
        return { 'result': { "success": True, "error": None } }
    localPath = backup_fs.ToPath(pathID)
    if localPath == restorePath:
        restorePath = os.path.dirname(restorePath)
    def _itemRestored(backupID, result): 
        backup_fs.ScanID(packetid.SplitBackupID(backupID)[0])
        backup_fs.Calculate()
    restore_monitor.Start(backupID, restorePath, _itemRestored) 
    return { 'result': { "success": True, "error": None } }


def _delete(params):
    # localPath = params['path'].lstrip('/')
    pathID = params['id']
    if not packetid.Valid(pathID):
        return { 'result': { "success": False, "error": "path %s is not valid" % pathID} }
    if not backup_fs.ExistsID(pathID):
        return { 'result': { "success": False, "error": "path %s not found" % pathID} }
    backup_control.DeletePathBackups(pathID, saveDB=False, calculate=False)
    backup_fs.DeleteLocalDir(settings.getLocalBackupsDir(), pathID)
    backup_fs.DeleteByID(pathID)
    backup_fs.Scan()
    backup_fs.Calculate()
    backup_control.Save()
    control.request_update([('pathID', pathID),])
    backup_monitor.A('restart')
    return { 'result': { "success": True, "error": None } }
    

def _delete_version(params):
    lg.out(6, '_delete_version %s' % str(params))
    backupID = params['backupid']
    if not packetid.Valid(backupID):
        return { 'result': { "success": False, "error": "backupID %s is not valid" % backupID} }
    pathID, version = packetid.SplitBackupID(backupID)
    if not backup_fs.ExistsID(pathID):
        return { 'result': { "success": False, "error": "path %s not found" % pathID} }
    if version:
        backup_control.DeleteBackup(backupID, saveDB=False, calculate=False)
    backup_fs.Scan()
    backup_fs.Calculate()
    backup_control.Save()
    backup_monitor.A('restart')
    control.request_update([('backupID', backupID),])
    return { 'result': { "success": True, "error": None } }
    

def _rename(params):
    return { 'result': { "success": False, "error": "not done yet" } }


def _list_active_tasks(params):
    result = []
    for tsk in backup_control.ListPendingTasks():
        result.append({
            'name': os.path.basename(tsk.localPath),
            'path': os.path.dirname(tsk.localPath),
            'id': tsk.pathID,
            'version': '',
            'mode': 'up',
            'progress': '0%' })
    for backupID in backup_control.ListRunningBackups():
        backup_obj = backup_control.GetRunningBackupObject(backupID)
        pathID, versionName = packetid.SplitBackupID(backupID)
        result.append({
            'name': os.path.basename(backup_obj.sourcePath),
            'path': os.path.dirname(backup_obj.sourcePath),
            'id': pathID,
            'version': versionName,
            'mode': 'up',
            'progress': misc.percent2string(backup_obj.progress()), })
    # for backupID in restore_monitor.GetWorkingIDs():
    #     result.append(backupID)
    return { 'result': result, }

def _list_packet_transfers(params):
    result = []
    for pkt_out in packet_out.queue():
        result.append({
            'name': pkt_out.label,
            'progress': pkt_out.percent_sent(),
            'to': pkt_out.remote_idurl,
            })
    for pkt_in in packet_in.items().values():
        result.append({
            'name': pkt_in.label,
            'progress': pkt_in.percent_received(),
            'from': pkt_in.sender_idurl,
            })
    return { 'result': result, }

def _debuginfo(params):
    result = {}
    result['debug'] = lg.get_debug_level()
    result['automats'] = []
    from automats import automat 
    for index, A in automat.objects().items():
        result['automats'].append({
            'index': index,
            'id': A.id,
            'name': A.name,
            'state': A.state, })
    return { 'result': result, }
    

