#!/usr/bin/python
# dht_service.py
#
# Copyright (C) 2008-2018 Veselin Penev, https://bitdust.io
#
# This file (dht_service.py) is part of BitDust Software.
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
..

module:: dht_service
"""

#------------------------------------------------------------------------------

_Debug = True
_DebugLevel = 6

#------------------------------------------------------------------------------

import sys
import hashlib
import random
import base64
import optparse
import json

from twisted.internet import reactor
from twisted.internet.defer import Deferred, fail

from entangled.dtuple import DistributedTupleSpacePeer
from entangled.kademlia.datastore import SQLiteDataStore
from entangled.kademlia.node import rpcmethod
from entangled.kademlia.protocol import KademliaProtocol, encoding, msgformat

#------------------------------------------------------------------------------

if __name__ == '__main__':
    import os.path as _p
    sys.path.insert(0, _p.abspath(_p.join(_p.dirname(_p.abspath(sys.argv[0])), '..')))

#------------------------------------------------------------------------------

from logs import lg

from system import bpio

from main import settings

from dht import known_nodes

#------------------------------------------------------------------------------

_MyNode = None
_ActiveLookup = None

#------------------------------------------------------------------------------


def init(udp_port, db_file_path=None):
    global _MyNode
    if _MyNode is not None:
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.init SKIP, already created a DHTNode')
        return
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.init UDP port is %d' % udp_port)
    if db_file_path is None:
        db_file_path = settings.DHTDBFile()
    dbPath = bpio.portablePath(db_file_path)
    lg.out(4, 'dht_service.init UDP port is %d, DB file path: %s' % (udp_port, dbPath))
    dataStore = SQLiteDataStore(dbFile=dbPath)
    networkProtocol = KademliaProtocolConveyor
    # None, encoding.Bencode(), msgformat.DefaultFormat())
    _MyNode = DHTNode(udp_port, dataStore, networkProtocol=networkProtocol)
    # _MyNode._protocol.node = _MyNode


def shutdown():
    global _MyNode
    if _MyNode is not None:
        _MyNode._dataStore._db.close()
        _MyNode._protocol.node = None
        del _MyNode
        _MyNode = None
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.shutdown')
    else:
        lg.warn('DHTNode not exist')

#------------------------------------------------------------------------------


def node():
    global _MyNode
    return _MyNode


def connect():
    result = Deferred()

    if not node().listener:
        node().listenUDP()

    if node().refresher and node().refresher.active():
        node().refresher.reset(0)
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.connect DHT already active : SKIP but RESET refresher task')
        result.callback(True)
        return result

    def _on_join_success(ok):
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.connect DHT JOIN SUCCESS !!!!!!!!!!!!!!!!!!!!!!!')
        result.callback(True)

    def _on_join_failed(x):
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.connect DHT JOIN FAILED : %s' % x)
        result.callback(False)

    def _on_hosts_resolved(live_nodes):
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.connect RESOLVED %d live nodes' % (len(live_nodes)))
            for onenode in live_nodes:
                lg.out(_DebugLevel, '    %s:%s' % onenode)
        node().joinNetwork(live_nodes)
        node()._joinDeferred.addCallback(_on_join_success)
        node()._joinDeferred.addErrback(_on_join_failed)
        return live_nodes

    def _on_hosts_resolve_failed(x):
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.connect ERROR : hosts not resolved: %s' % x)
        result.callback(False)
        return x

    _known_nodes = known_nodes.nodes()
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.connect STARTING with %d known nodes:' % (len(_known_nodes)))
        for onenode in _known_nodes:
            lg.out(_DebugLevel, '    %s:%s' % onenode)

    d = resolve_hosts(_known_nodes)
    d.addCallback(_on_hosts_resolved)
    d.addErrback(_on_hosts_resolve_failed)

    return result


def disconnect():
    global _MyNode
    if not node():
        return False
    if node().refresher and node().refresher.active():
        node().refresher.cancel()
    node().listener.stopListening()
    return True


def reconnect():
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.reconnect')
    return node().reconnect()

#------------------------------------------------------------------------------

def on_host_resoled(ip, port, host, result_list, total_hosts, result_defer):
    if not isinstance(ip, str) or port is None:
        result_list.append(None)
        lg.warn('"%s" failed to resolve' % host)
    else:
        result_list.append((ip, port, ))
    if len(result_list) != total_hosts:
        return None
    return result_defer.callback(filter(None, result_list))


def resolve_hosts(nodes_list):
    result_defer = Deferred()
    result_list = []
    for node_tuple in nodes_list:
        d = reactor.resolve(node_tuple[0])
        d.addCallback(on_host_resoled, node_tuple[1], node_tuple[0], result_list, len(nodes_list), result_defer)
        d.addErrback(on_host_resoled, None, node_tuple[0], result_list, len(nodes_list), result_defer)
    return result_defer

#------------------------------------------------------------------------------

def random_key():
    return key_to_hash(str(random.getrandbits(255)))


def key_to_hash(key):
    h = hashlib.sha1()
    h.update(key)
    return h.digest()

#------------------------------------------------------------------------------

def on_success(result, method, key, arg=None):
    if isinstance(result, dict):
        v = str(result.values())
    else:
        v = 'None'
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.on_success   %s(%s)   result=%s' % (
            method, key, v[:20].replace('\n', '')))
    return result


def on_error(err, method, key):
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.on_error %s(%s) returned an ERROR:\n%s' % (method, key, str(err)))
    return err

#------------------------------------------------------------------------------

def get_value(key):
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.get_value key=[%s]' % key)
    if not node():
        return fail(Exception('DHT service is off'))
    d = node().iterativeFindValue(key_to_hash(key))
    d.addCallback(on_success, 'get_value', key)
    d.addErrback(on_error, 'get_value', key)
    return d


def set_value(key, value, age=0):
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.set_value key=[%s] value=[%s]' % (
            key, str(value).replace('\n', '')))
    if not node():
        return fail(Exception('DHT service is off'))
    d = node().iterativeStore(key_to_hash(key), value, age=age)
    d.addCallback(on_success, 'set_value', key, value)
    d.addErrback(on_error, 'set_value', key)
    return d


def delete_key(key):
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.delete_key [%s]' % key)
    if not node():
        return fail(Exception('DHT service is off'))
    d = node().iterativeDelete(key_to_hash(key))
    d.addCallback(on_success, 'delete_value', key)
    d.addErrback(on_error, 'delete_key', key)
    return d

#------------------------------------------------------------------------------

def read_json_response(response, key, result_defer=None):
    value = None
    if isinstance(response, dict):
        try:
            value = json.loads(response[key])
        except:
            lg.exc()
            if result_defer:
                result_defer.errback(Exception('invalid json value'))
            return
    if result_defer:
        result_defer.callback(value)
    return value


def get_json_value(key):
    if not node():
        return fail(Exception('DHT service is off'))
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.get_value key=[%s]' % key)
    ret = Deferred()
    d = get_value(key)
    d.addCallback(read_json_response, key_to_hash(key), ret)
    d.addErrback(ret.errback)
    return ret


def set_json_value(key, json_data, age=0):
    if not node():
        return fail(Exception('DHT service is off'))
    try:
        value = json.dumps(json_data, indent=0, sort_keys=True, separators=(',', ':'), encoding='utf-8')
    except:
        return fail(Exception('bad input json data'))
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.set_json_value key=[%s] value=[%s]' % (
            key, str(value).replace('\n', '')))
    return set_value(key=key, value=value, age=age)

#------------------------------------------------------------------------------

def validate_data(value, rules, result_defer=None):
    if not isinstance(value, dict):
        if result_defer:
            result_defer.errback(Exception('value not found'))
        return None
    passed = True
    for field, field_rules in rules.items():
        for rule in field_rules:
            if 'op' not in rule:
                continue
            if rule['op'] == 'equal' and rule.get('arg') != value.get(field):
                passed = False
                break
            if rule['op'] == 'exist' and field not in value:
                passed = False
                break
        if not passed:
            break
    if not passed:
        lg.warn('invalid data in response, validation rules failed')
        if result_defer:
            result_defer.errback(Exception('invalid value in response'))
        return None
    if result_defer:
        result_defer.callback(value)
    return value


def get_valid_data(key, rules={}):
    if not node():
        return fail(Exception('DHT service is off'))
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.get_valid_data key=%s rules=%s' % (key, rules, ))
    ret = Deferred()
    d = get_json_value(key)
    d.addCallback(validate_data, rules, ret)
    d.addErrback(ret.errback)
    return ret


def set_valid_data(key, json_data, age=0, rules={}):
    if validate_data(json_data, rules) is None:
        return fail(Exception('invalid data, validation failed'))
    return set_json_value(key, json_data=json_data, age=age)

#------------------------------------------------------------------------------

def on_nodes_found(result, node_id64):
    on_success(result, 'find_node', node_id64)
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.on_nodes_found   node_id=[%s], %d nodes found' % (node_id64, len(result)))
    return result

def on_lookup_failed(result, node_id64):
    on_error(result, 'find_node', node_id64)
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.on_lookup_failed   node_id=[%s], result=%s' % (node_id64, result))
    return result

def find_node(node_id):
    global _ActiveLookup
    if _ActiveLookup and not _ActiveLookup.called:
        if _Debug:
            lg.out(_DebugLevel, 'dht_service.find_node SKIP, already started')
        return _ActiveLookup
    node_id64 = base64.b64encode(node_id)
    if _Debug:
        lg.out(_DebugLevel, 'dht_service.find_node   node_id=[%s]' % node_id64)
    if not node():
        return fail(Exception('DHT service is off'))
    _ActiveLookup = node().iterativeFindNode(node_id)
    _ActiveLookup.addErrback(on_lookup_failed, node_id64)
    _ActiveLookup.addCallback(on_nodes_found, node_id64)
    return _ActiveLookup

#------------------------------------------------------------------------------

def get_node_data(key):
    if not node():
        return None
    if key not in node().data:
        return None
    value = node().data[key]
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.get_node_data key=[%s] returning: %s' % (key, str(value)))
    return value


def set_node_data(key, value):
    if not node():
        return False
    node().data[key] = value
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.set_node_data key=[%s] value: %s' % (key, str(value)))
    return True


def delete_node_data(key):
    if not node():
        return False
    if key not in node().data:
        return False
    node().data.pop(key)
    if _Debug:
        lg.out(_DebugLevel + 10, 'dht_service.delete_node_data key=[%s]' % key)
    return True

#------------------------------------------------------------------------------

class DHTNode(DistributedTupleSpacePeer):

    def __init__(self, udpPort=4000, dataStore=None, routingTable=None, networkProtocol=None):
        super(DHTNode, self).__init__(udpPort, dataStore, routingTable, networkProtocol)
        self.data = {}

    @rpcmethod
    def store(self, key, value, originalPublisherID=None, age=0, **kwargs):
        if _Debug:
            lg.out(_DebugLevel + 10, 'dht_service.DHTNode.store key=[%s], value=[%s]' % (
                base64.b32encode(key), str(value).replace('\n', '')))
        # TODO: add verification methods for different type of data we store in DHT
        # TODO: add signature validation to be sure this is the owner of that key:value pair
        self.data[key] = value
        try:
            return super(DHTNode, self).store(
                key,
                value,
                originalPublisherID=originalPublisherID,
                age=age,
                **kwargs
            )
        except:
            lg.exc()
            return 'OK'

    @rpcmethod
    def request(self, key):
        value = self.data.get(key)
        if value is None and key in self._dataStore:
            value = self._dataStore[key]
            self.data[key] = value
        if _Debug:
            lg.out(_DebugLevel + 10, 'dht_service.DHTNode.request key=[%s], return value=[%s]' % (
                base64.b32encode(key), str(value)[:20]))
        return {key: value, }

    def reconnect(self, knownNodeAddresses=None):
        """
        TODO: need to restart _scheduleNextNodeRefresh.
        """
        d = Deferred()
        if not self.listener:
            d.errback('Listener not started yet')
            return d
        if self.refresher and self.refresher.active():
            self.refresher.reset(0)
        d.callback(1)
        return d

#------------------------------------------------------------------------------


class KademliaProtocolConveyor(KademliaProtocol):

    def __init__(self, node, msgEncoder=encoding.Bencode(), msgTranslator=msgformat.DefaultFormat()):
        KademliaProtocol.__init__(self, node, msgEncoder, msgTranslator)
        self.datagrams_queue = []
        self.worker = None

    def datagramReceived(self, datagram, address):
        if len(self.datagrams_queue) > 10:
            # TODO:
            # seems like DHT traffic is too high at that moment
            # need to find some solution here probably
            return
        self.datagrams_queue.append((datagram, address))
        if self.worker is None:
            self.worker = reactor.callLater(0, self._process)

    def _process(self):
        if len(self.datagrams_queue) == 0:
            self.worker = None
            return
        # if _Debug:
        #     print '                dht._process, queue length:', len(self.datagrams_queue)
        datagram, address = self.datagrams_queue.pop(0)
        KademliaProtocol.datagramReceived(self, datagram, address)
        self.worker = reactor.callLater(0.005, self._process)

#------------------------------------------------------------------------------


def parseCommandLine():
    oparser = optparse.OptionParser()
    oparser.add_option("-p", "--udpport", dest="udpport", type="int", help="specify UDP port for DHT network")
    oparser.set_default('udpport', settings.DefaultDHTPort())
    oparser.add_option("-d", "--dhtdb", dest="dhtdb", help="specify DHT database file location")
    oparser.set_default('dhtdb', settings.DHTDBFile())
    (options, args) = oparser.parse_args()
    return options, args


def main():
    bpio.init()
    settings.init()
    lg.set_debug_level(28)
    (options, args) = parseCommandLine()
    init(options.udpport, options.dhtdb)

    def _go(nodes):
        try:
            if len(args) == 0:
                pass
            elif len(args) > 0:
                def _r(x):
                    print x
                    reactor.stop()
                cmd = args[0]
                if cmd == 'get':
                    get_value(args[1]).addBoth(_r)
                elif cmd == 'set':
                    set_value(args[1], args[2]).addBoth(_r)
                if cmd == 'get_json':
                    get_json_value(args[1]).addBoth(_r)
                elif cmd == 'set_json':
                    set_json_value(args[1], args[2]).addBoth(_r)
                if cmd == 'get_valid_data':
                    get_valid_data(args[1], rules=json.loads(args[2])).addBoth(_r)
                elif cmd == 'set_valid_data':
                    set_valid_data(args[1], json.loads(args[2]), rules=json.loads(args[3])).addBoth(_r)
                elif cmd == 'find':
                    find_node(key_to_hash(args[1])).addBoth(_r)
                elif cmd == 'discover':
                    def _l(x):
                        print x
                        find_node(random_key()).addBoth(_l)
                    _l('')
        except:
            lg.exc()

    connect().addBoth(_go)
    reactor.run()

#------------------------------------------------------------------------------


if __name__ == '__main__':
    main()
