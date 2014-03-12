PowerPool Agent
===============
A statistics collection agent for the PowerPool mining server. It was built to
work with `Simple Doge mining pool <http://simpledoge.com>`_ . Currently only
available for linux distributions running python 2.6 or 2.7. Tested on cgminer
3.7.2 and sgminer 4.1.0, may work for other cgminer derivatives.

Installation
^^^^^^^^^^^^

Make sure your cgminer or sgminer is running with the api port enabled. This
can be done on command line with the ``--api-listen`` argument, or in your
configuration file with ``"api-listen": true``.

Ubuntu:

.. code-block:: bash

    sudo pip install ppagent
    sudo ppagent install upstart

Windows:

#. `Download latest binary <https://github.com/icook/ppagent/releases/download/v0.2.5/ppagent.exe>`_.
#. Run the binary at the same time cgminer is running and connected to stratum.simpledoge.com and status will be automatically reported.
    
Debian (for BAMT or SMOS):

.. code-block:: bash

    sudo pip install ppagent
    sudo ppagent install sysv
    
Now when your miner is running against stratum.simpledoge.com the daemon will
automatically start sending statistics to the server as well. Check your stats
page on SimpleDoge to see that it's working. You should see something similar
to this:

.. image:: https://github.com/icook/ppagent/raw/master/doc/worker_stat.png
    :alt: Worker status display
    :width: 276
    :height: 153
    :align: center


Upgrade
^^^^^^^^^^^^

Ubuntu:

.. code-block:: bash

    sudo pip install --upgrade ppagent
    sudo service ppagent restart
    
Debian (for BAMT or SMOS):

.. code-block:: bash

    sudo pip install --upgrade ppagent
    sudo /etc/init.d/ppagent stop
    sudo /etc/init.d/ppagent start
    
Troubleshooting
^^^^^^^^^^^^^^^
If it's not showing up after a minute or two you should first check the logs.
On debian these are at:

.. code-block:: bash

    /var/log/ppagent.log
    
On Ubuntu:

.. code-block:: bash

    /var/log/upstart/ppagent.log
    
The error messages should give you a clue why it's not working.
If not, login to the `simple doge IRC <https://kiwiirc.com/client/irc.freenode.net/#simpledoge>`_
and we'll try to help you get is straightened out.

Non-Standard Configurations
^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you're not running cgminer on the same computer as ppagent, or you're running on a non-standard port you'll have to tweak the configuration file a little bit.

On **Linux**, the configuration file is in:

.. code-block:: bash

    /etc/ppagent/config.json
    
On **Windows** it will automatically look in the same folder as the executable, and it will be named ``ppagent.json``.

Your default configuration file should look like this:

.. code-block:: json

    [
        {"miner":
            {
                "type": "CGMiner"
            }
        }
    ]

However, this is automatically getting filled in with defaults. If all the defaults were defined here, they would look something like this:

.. code-block:: json

    [
        {"miner":
            {
                "type": "CGMiner",
                        "port": 4028,  # port to connect to cgminer api
                        "address": "127.0.0.1",  # address to connect to cgminer api
                        "collectors": {  # list of data collectors and their configurations
                                "status": {
                                        "enabled": true,
                                        "temperature": true,
                                        "mhps": true,
                                        "details": true,
                                        "interval": 60
                                },
                                "temp": {
                                        "enabled": true,
                                        "interval": 60
                                },
                                "hashrate": {
                                        "enabled": true,
                                        "interval": 60
                                }
                        }
                }
        }
    ]

For example, if you wanted to change the port your cgminer was running on, you would enter something like this:

.. code:: json

    [
        {"miner":
            {
                "type": "CGMiner",
                "port": 4029  # this is not the default!
            }
        }
    ]

Or if you wanted to report the status of two different cgminer instances

.. code:: json

    [
        {"miner":
            {
                "type": "CGMiner",
                "port": 4028  # first one is running on the default port
            }
        },
        {"miner":
            {
                "type": "CGMiner",
                "port": 4029  # second one is running on a non-standard port
            }
        }
    ]

Both miners will be assumed to be running locally, but that too can be overriden by specifying a non-default ``"address"`` value.
