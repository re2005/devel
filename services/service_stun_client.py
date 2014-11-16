#!/usr/bin/python
#service_stun_client.py
#
# <<<COPYRIGHT>>>
#
#
#
#

"""
.. module:: service_stun_client

"""

from services.local_service import LocalService

def create_service():
    return StunClientService()
    
class StunClientService(LocalService):
    
    service_name = 'service_stun_client'
    config_path = 'services/stun-client/enabled'
    
    def init(self):
        self._my_address = None
    
    def dependent_on(self):
        return ['service_entangled_dht',
                'service_udp_datagrams',
                ]
    
    def start(self):
        from stun import stun_client
        from lib import settings
        from twisted.internet.defer import Deferred
        stun_client.A('init', settings.getUDPPort())
        d = Deferred()
        stun_client.A('start', 
            lambda result, typ, ip, details: 
                self.on_stun_client_finished(result, typ, ip, details, d))
        return d
    
    def stop(self):
        from stun import stun_client
        stun_client.A('shutdown')
        return True
    
    def on_stun_client_finished(self, result, typ, ip, details, result_defer):
        from stun import stun_client
        # if result == 'stun-success':
        result_defer.callback(stun_client.A().getMyExternalAddress()) 
        # else:
        #     result_defer.callback()

