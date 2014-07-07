

"""
.. module:: packet_out
.. role:: red

BitPie.NET packet_out() Automat

.. raw:: html

    <a href="packet_out.png" target="_blank">
    <img src="packet_out.png" style="max-width:100%;">
    </a>

EVENTS:
    * :red:`cancel`
    * :red:`failed`
    * :red:`inbox-packet`
    * :red:`item-cancelled`
    * :red:`items-sent`
    * :red:`nothing-to-send`
    * :red:`register-item`
    * :red:`remote-identity-on-hand`
    * :red:`run`
    * :red:`unregister-item`
    * :red:`write-error`
"""

import os
import time
import hashlib

import lib.dhnio as dhnio
import lib.automat as automat
import lib.misc as misc
import lib.commands as commands
import lib.contacts as contacts
import lib.tmpfile as tmpfile
import lib.nameurl as nameurl
import lib.settings as settings
import lib.dhnnet as dhnnet

import userid.identitycache as identitycache

import callback
import gate
import stats

#------------------------------------------------------------------------------ 

_OutboxQueue = []

#------------------------------------------------------------------------------ 

def queue():
    """
    """
    global _OutboxQueue
    return _OutboxQueue


def create(outpacket, doack, wide):
    """
    """
    dhnio.Dprint(10, 'packet_out.create  %s' % str(outpacket))
    p = PacketOut(outpacket, doack, wide)
    queue().append(p)
    p.automat('run', (outpacket, doack, wide))
    return p
    
    
def search(proto, host, filename):
    # print 'search', proto, host, filename
    for p in queue():
        if p.filename != filename:
            # print p.filename
            continue
        for i in p.items:
            # print i.host, i.proto
            if i.host == host and i.proto == proto:
                return p, i
    return None, None


def search_by_transfer_id(transfer_id):
    for p in queue():
        for i in p.items:
            if i.transfer_id and i.transfer_id == transfer_id:
                return p, i
    return None, None


def search_by_packet_id(creator_id, packet_id):
    result = []
    for p in queue():
        # print p.outpacket.CreatorID, p.outpacket.PacketID, creator_id, packet_id
        if p.outpacket.RemoteID == creator_id and p.outpacket.PacketID == packet_id:
            result.append(p)
    return result

#------------------------------------------------------------------------------ 

class WorkItem:
    def __init__(self, proto, host):
        self.proto = proto
        self.host = host
        self.time = time.time()
        self.transfer_id = None
        self.status = None
        self.error_message = None
        self.bytes_sent = 0


class PacketOut(automat.Automat):
    """
    This class implements all the functionality of the ``packet_out()`` state machine.
    """
    
    def __init__(self, outpacket, wide, callbacks={}):
        self.time = time.time()
        self.outpacket = outpacket
        self.wide = wide
        self.callbacks = callbacks
        self.description = self.outpacket.Command+'('+self.outpacket.PacketID+')'
        self.payloadsize = len(self.outpacket.Payload)
        if self.outpacket.CreatorID == misc.getLocalID():
            self.remote_idurl = self.outpacket.RemoteID.strip()
        else:
            if self.outpacket.Command == commands.Data():      
                self.remote_idurl = self.outpacket.CreatorID.strip()       
            else:
                self.remote_idurl = None
                dhnio.Dprint(2, 'packet_out.__init__ WARNING sending a packet we did not make, and that is not Data packet')
        self.remote_identity = contacts.getContact(self.remote_idurl)
        self.hash = '%s%s%s%s' % (str(self.time), self.outpacket.Command, 
                                  self.outpacket.PacketID, str(self.remote_idurl))
        h = hashlib.md5()
        h.update(self.hash)
        self.md5 = h.hexdigest()
        self.timeout = None
        self.packetdata = None
        self.filename = None
        self.filesize = None
        self.items = []
        self.results = []
        self.response_packet = None
        automat.Automat.__init__(self, 'OUT(%s)' % self.md5, 'AT_STARTUP', 8)
        
    def is_timed_out(self):
        if self.time is None or self.timeout is None:
            return False
        return time.time() - self.time > self.timeout
        
    def set_callback(self, command, cb):
        self.callbacks[command] = cb
        
    def state_changed(self, oldstate, newstate):
        """
        Method to to catch the moment when automat's state were changed.
        """

    def A(self, event, arg):
        #---SENDING---
        if self.state == 'SENDING':
            if event == 'register-item' :
                self.doSetTransferID(arg)
            elif ( event == 'unregister-item' or event == 'item-cancelled' ) and not self.isMoreItems(arg) and ( self.Acked or not self.isAckNeeded(arg) ) :
                self.state = 'SENT'
                self.doPopItem(arg)
                self.doReportItem(arg)
                self.doReportDoneNoAck(arg)
                self.doDestroyMe(arg)
            elif event == 'cancel' :
                self.state = 'CANCEL'
                self.doCancelItems(arg)
                self.doReportCancelItems(arg)
                self.doPopItems(arg)
                self.doReportCancelled(arg)
                self.doDestroyMe(arg)
            elif ( event == 'unregister-item' or event == 'item-cancelled' ) and self.isMoreItems(arg) :
                self.doPopItem(arg)
                self.doReportItem(arg)
            elif event == 'inbox-packet' and self.isResponse(arg) :
                self.Acked=True
                self.doSaveResponse(arg)
            elif event == 'unregister-item' and not self.isMoreItems(arg) and self.isAckNeeded(arg) and not self.Acked :
                self.state = 'RESPONSE?'
                self.doPopItem(arg)
                self.doReportItem(arg)
        #---AT_STARTUP---
        elif self.state == 'AT_STARTUP':
            if event == 'run' and self.isRemoteIdentityKnown(arg) :
                self.state = 'ITEMS?'
                self.doInit(arg)
                self.doReportStarted(arg)
                self.doSerializeAndWrite(arg)
                self.doPushItems(arg)
            elif event == 'run' and not self.isRemoteIdentityKnown(arg) :
                self.state = 'CACHING'
                self.doInit(arg)
                self.doCacheRemoteIdentity(arg)
        #---CACHING---
        elif self.state == 'CACHING':
            if event == 'remote-identity-on-hand' :
                self.state = 'ITEMS?'
                self.doReportStarted(arg)
                self.doSerializeAndWrite(arg)
                self.doPushItems(arg)
            elif event == 'failed' :
                self.state = 'FAILED'
                self.doReportFailed(arg)
                self.doDestroyMe(arg)
        #---FAILED---
        elif self.state == 'FAILED':
            pass
        #---ITEMS?---
        elif self.state == 'ITEMS?':
            if event == 'items-sent' :
                self.state = 'IN_QUEUE'
            elif event == 'nothing-to-send' or event == 'write-error' :
                self.state = 'FAILED'
                self.doReportFailed(arg)
                self.doDestroyMe(arg)
        #---IN_QUEUE---
        elif self.state == 'IN_QUEUE':
            if event == 'register-item' :
                self.state = 'SENDING'
                self.Acked=False
                self.doSetTransferID(arg)
            elif event == 'item-cancelled' and not self.isMoreItems(arg) :
                self.state = 'FAILED'
                self.doPopItem(arg)
                self.doReportItem(arg)
                self.doReportFailed(arg)
                self.doDestroyMe(arg)
            elif event == 'item-cancelled' and self.isMoreItems(arg) :
                self.doPopItem(arg)
            elif event == 'cancel' :
                self.state = 'CANCEL'
                self.doCancelItems(arg)
                self.doReportCancelItems(arg)
                self.doPopItems(arg)
                self.doReportCancelled(arg)
                self.doDestroyMe(arg)
        #---SENT---
        elif self.state == 'SENT':
            pass
        #---CANCEL---
        elif self.state == 'CANCEL':
            pass
        #---RESPONSE?---
        elif self.state == 'RESPONSE?':
            if event == 'cancel' :
                self.state = 'CANCEL'
                self.doReportCancelItems(arg)
                self.doReportCancelled(arg)
                self.doDestroyMe(arg)
            elif event == 'inbox-packet' and self.isResponse(arg) :
                self.state = 'SENT'
                self.doSaveResponse(arg)
                self.doReportDoneWithAck(arg)
                self.doDestroyMe(arg)

    def isRemoteIdentityKnown(self, arg):
        """
        Condition method.
        """
        return self.remote_identity is not None

    def isAckNeeded(self, arg):
        """
        Condition method.
        """
        return len(self.callbacks) > 0

    def isMoreItems(self, arg):
        """
        Condition method.
        """
        return len(self.items) > 1

    def isResponse(self, arg):
        """
        Condition method.
        """
        newpacket = arg
        return newpacket.Command in self.callbacks.keys()

    def doInit(self, arg):
        """
        Action method.
        """
        self.outpacket, self.doack, self.wide = arg

    def doCacheRemoteIdentity(self, arg):
        """
        Action method.
        """
        d = identitycache.immediatelyCaching(self.remote_idurl)
        d.addCallback(self._remote_identity_cached)
        d.addErrback(lambda err: self.automat('failed'))

    def doSerializeAndWrite(self, arg):
        """
        Action method.
        """
        # serialize and write dhnpacket on disk
        try:
            fileno, self.filename = tmpfile.make('outbox')
            self.packetdata = self.outpacket.Serialize()
            os.write(fileno, self.packetdata)
            os.close(fileno)
            self.filesize = len(self.packetdata)
            self.timeout = max(int(self.filesize/settings.SendingSpeedLimit()), settings.SendTimeOut())
        except:
            dhnio.DprintException()
            self.packetdata = None
            self.automat('write-error')
            
    def doPushItems(self, arg):
        """
        Action method.
        """
        self._push()

    def doPopItem(self, arg):
        """
        Action method.
        """
        self.popped_item = None
        if len(arg) == 4:
            transfer_id, status, size, error_message = arg
            for i in self.items:
                if i.transfer_id and i.transfer_id == transfer_id:
                    # self._item_finished(i, status, size, error_message)
                    self.items.remove(i)
                    i.status = status
                    i.error_message = error_message
                    i.bytes_sent = size
                    self.results.append(i)
                    # self.results.append((i.proto, i.host, status, size, '', error_message))
                    self.popped_item = i
                    break
        elif len(arg) == 6:
            proto, host, filename, size, descr, err_msg = arg
            for i in self.items:
                if i.proto == proto and i.host == host:
                    # self._item_failed(i)
                    self.items.remove(i)
                    i.status = 'failed'
                    i.error_message = err_msg
                    i.bytes_sent = size
                    self.results.append(i)
                    # self.results.append((i.proto, i.host, 'failed', size, descr, err_msg))
                    self.popped_item = i
                    break
        else:
            raise Exception('Wrong argument!')
            
    def doPopItems(self, arg):
        """
        Action method.
        """
        self.items = []

    def doSetTransferID(self, arg):
        """
        Action method.
        """
        ok = False
        proto, host, filename, transfer_id = arg
        for i in xrange(len(self.items)):
            if self.items[i].proto == proto and self.items[i].host == host:
                self.items[i].transfer_id = transfer_id
                dhnio.Dprint(18, 'packet_out.doSetTransferID  %r:%r = %r' % (proto, host, transfer_id))
                ok = True
        if not ok:
            dhnio.Dprint(8, 'packet_out.doSetTransferID WARNING not found item for %r:%r' % (proto, host))

    def doSaveResponse(self, arg):
        """
        Action method.
        """
        self.response_packet = arg

    def doCancelItems(self, arg):
        """
        Action method.
        """
        for i in self.items:
            if i.transfer_id:
                gate.transport(i.proto).call('cancel_file_sending', i.transfer_id)
            else:
                gate.transport(i.proto).call('cancel_outbox_file', i.host, self.filename)
                
    def doReportStarted(self, arg):
        """
        Action method.
        """
        callback.run_outbox_callbacks(self.outpacket, self.doack, self.wide)

    def doReportItem(self, arg):
        """
        Action method.
        """
        assert self.popped_item
        stats.count_outbox(
            self.remote_idurl, self.popped_item.proto, 
            self.popped_item.status, self.popped_item.bytes_sent)
        callback.run_finish_file_sending_callbacks(
            self, self.popped_item, self.popped_item.status, 
            self.popped_item.bytes_sent, self.popped_item.error_message)
        self.popped_item = None

    def doReportCancelItems(self, arg):
        """
        Action method.
        """
        msg = arg
        if not isinstance(msg, str):
            msg = 'cancelled'
        for item in self.results:
            stats.count_outbox(self.remote_idurl, item.proto, 'failed', 0)
            callback.run_finish_file_sending_callbacks(
                self, item, 'failed', 0, msg)

    def doReportDoneWithAck(self, arg):
        """
        Action method.
        """
        if self.response_packet.Command == commands.Ack():
            for cb in self.ack_callbacks:
                cb(self.response_packet, self)
        elif self.response_packet.Command == commands.Fail():
            for cb in self.fail_callbacks:
                cb(self.response_packet, self)
        else:
            raise Exception('wrong type of response packet')
        self.ack_callbacks = []
        self.fail_callbacks = []
        callback.run_queue_item_status_callbacks(self, 'finished', '')

    def doReportDoneNoAck(self, arg):
        """
        Action method.
        """
        callback.run_queue_item_status_callbacks(self, 'finished', '')

    def doReportFailed(self, arg):
        """
        Action method.
        """
        try:
            msg = str(arg[-1])
        except:
            msg = 'failed'
        callback.run_queue_item_status_callbacks(self, 'failed', msg)

    def doReportCancelled(self, arg):
        """
        Action method.
        """
        msg = arg
        if not isinstance(msg, str):
            msg = 'cancelled'
        callback.run_queue_item_status_callbacks(self, 'failed', msg)

    def doDestroyMe(self, arg):
        """
        Remove all references to the state machine object to destroy it.
        """
        self.outpacket = None
        self.remote_identity = None
        self.callbacks.clear()
        self.fail_callbacks = []
        queue().remove(self)
        automat.objects().pop(self.index)

    def _remote_identity_cached(self, xmlsrc):
        self.remote_identity = contacts.getContact(self.remote_idurl)
        if self.remote_identity is None:
            self.automat('failed')
        else:
            self.automat('remote-identity-on-hand')

    def _push(self):
        # get info about his local IP
        localIP = identitycache.GetLocalIP(self.remote_idurl)
        workitem_sent = False
        if self.wide: 
            # send to all his contacts
            for contactmethod in self.remote_identity.getContacts():
                proto, host = nameurl.IdContactSplit(contactmethod)
                if  host.strip() and \
                    settings.transportSendingIsEnabled(proto) and \
                    gate.can_send(proto) and \
                    gate.is_installed(proto):
                        if proto == 'tcp' and localIP:
                            host = localIP
                        gate.send_file(proto, host, self.filename, self.description)
                        self.items.append(WorkItem(proto, host))
                        workitem_sent = True
            if not workitem_sent:
                self.automat('nothing-to-send')
                dhnio.Dprint(6, 'packet_out._push  (wide)  WARNING no supported protocols with %s' % self.remote_idurl)
            else:
                self.automat('items-sent')
            return
        # send to one of his contacts,
        # now need to decide which transport to use
        # let's prepare his contacts first
        byproto = self.remote_identity.getContactsByProto()
        tcp_contact = byproto.get('tcp', None)
        dhtudp_contact = byproto.get('dhtudp', None)
        working_protos = stats.peers_protos().get(self.remote_idurl, set())
        # tcp seems to be the most stable proto
        # now let's check if we know his local IP and 
        # he enabled tcp in his settings to be able to receive packets from others 
        # try to send to his local IP first, not external
        if tcp_contact and localIP and settings.enableTCPsending():
            if gate.is_installed('tcp') and gate.can_send(proto):
                proto, host, port, fn = nameurl.UrlParse(tcp_contact)
                if port:
                    host = localIP+':'+str(port)
                gate.send_file(proto, host , self.filename, self.description)
                self.items.append(WorkItem(proto, host))
                self.automat('items-sent')
                return
        # tcp is the best proto - if it is working - this is the best case!!!
        if tcp_contact and 'tcp' in working_protos and settings.enableTCPsending():
            proto, host, port, fn = nameurl.UrlParse(tcp_contact)
            if host.strip() and gate.is_installed(proto) and gate.can_send(proto):  
                if port:
                    host = host+':'+str(port)
                gate.send_file(proto, host, self.filename, self.description)
                self.items.append(WorkItem(proto, host))
                self.automat('items-sent')
                return
        # dhtudp contact
        if dhtudp_contact and 'dhtudp' in working_protos and settings.enableDHTUDPsending():
            proto, host = nameurl.IdContactSplit(dhtudp_contact)
            if host.strip() and gate.is_installed('dhtudp') and gate.can_send(proto):
                gate.send_file(proto, host, self.filename, self.description)
                self.items.append(WorkItem(proto, host))
                self.automat('items-sent')
                return
        # finally use the first proto we supported if we can not find the best preferable method
        for contactmethod in self.remote_identity.getContacts():
            proto, host, port, fn = nameurl.UrlParse(contactmethod)
            if port:
                host = host+':'+str(port)
            # if method exist but empty - don't use it
            if host.strip() and settings.transportSendingIsEnabled(proto):
                # try sending with tcp even if it is switched off in the settings
                if gate.is_installed(proto) and gate.can_send(proto):
                    gate.send_file(proto, host, self.filename, self.description)
                    self.items.append(WorkItem(proto, host))
                    self.automat('items-sent')
                    return
        self.automat('nothing-to-send')
        dhnio.Dprint(6, 'packet_out._push WARNING no supported protocols with %s' % self.remote_idurl)
        
    def _item_finished(self, item, status, size, error_message):
        stats.count_outbox(self.remote_idurl, item.proto, status)
        gate.counters_out()['total_bytes'] += size
        if self.remote_idurl and self.remote_idurl.startswith('http://') and self.remote_idurl.endswith('.xml'): 
            if not gate.counters_out().has_key(self.remote_idurl):
                gate.counters_out()[self.remote_idurl] = 0
            gate.counters_out()[self.remote_idurl] += size
        else:
            gate.counters_out()['unknown_bytes'] += size
        if status == 'finished':
            if self.remote_idurl and self.remote_idurl.startswith('http://') and self.remote_idurl.endswith('.xml'): 
                gate.counters_out()['total_packets'] += 1
            else:
                gate.counters_out()['unknown_packets'] += 1
            dhnnet.ConnectionDone(self.filename, item.proto, 'sendStatusReport %s' % item.host)
        else:
            if self.remote_idurl and self.remote_idurl.startswith('http://') and self.remote_idurl.endswith('.xml'): 
                gate.counters_out()['failed_packets'] += 1
            dhnnet.ConnectionFailed(self.filename, item.proto, 'sendStatusReport %s' % item.host)
        callback.run_finish_file_sending_callbacks(
            self, item, status, size, error_message)
        # webtraffic.outbox(self, item, status)
        # bandwidth.OUTfile(self, status)

    def _item_failed(self, item):
        dhnnet.ConnectionFailed(self, item.proto, 'sendStatusReport %s' % item.host)
        callback.run_finish_file_sending_callbacks(
            self, item, 'failed', 0, None)
        

