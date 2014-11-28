#!/bin/bash

# configure apache2
sudo apt-get install apache2
sudo nano /etc/apache2/apache2.conf # add line "ServerName my-own-identity-server.com"
sudo cp -T id_server_apache2_conf /etc/apache2/conf.d/idserver
sudo a2enmod proxy_http 
sudo a2enmod rewrite
sudo service apache2 restart

# configure BitPie.NET
python bitpie.py set service/id-server/enabled true
python bitpie.py set service/id-server/host my-own-identity-server.com

# you can run only identity server: ./run.id_server
# or just start the whole BitPie.NET software in background
python bitpie.py detach