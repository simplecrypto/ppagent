PowerPool Agent
===============
A statistics collection agent for the PowerPool mining server. It was built to
work with `Simple Doge mining pool <http://simpledoge.com>`_ . Runs on Windows,
Ubuntu Linux and Debian Linux. Tested on cgminer 3.7.2 and sgminer 4.1.0,
should also work on other derivatives.

Installation
^^^^^^^^^^^^
Make sure your cgminer or sgminer is running with the api port enabled. ThiFs
can be done on command line with the ``--api-listen`` argument, or in your
configuration file with ``"api-listen": true``.

Ubuntu:
**************************
.. code-block:: bash

    # Install python and python package manager pip (frequently already installed)
    sudo apt-get install python python-pip
    sudo pip install ppagent
    sudo ppagent install upstart
ppagent will now start with your computer automatically.

Windows:
**************************
#. `Download latest exe <https://github.com/icook/ppagent/releases/download/v0.2.6/ppagent.exe>`_.
#. Run the binary when connected to stratum.simpledoge.com and status will be automatically reported.

To make ppagent start on boot, `see this post <http://superuser.com/questions/63326/enable-exe-to-run-at-startup>`_.
    
Debian (for BAMT or SMOS):
**************************
.. code-block:: bash

    # Install python and python package manager pip (frequently already installed)
    sudo apt-get install python python-pip
    sudo pip install ppagent
    sudo ppagent install sysv
ppagent will now start with your computer automatically.
    
======================================================================

Now when your miner is running against stratum.simpledoge.com the daemon will
automatically start sending statistics to the server as well. Check your stats
page on SimpleDoge to see that it's working. You should see something similar
to this:

.. image:: https://github.com/icook/ppagent/raw/master/doc/worker_stat.png
    :alt: Worker status display
    :width: 943
    :height: 234
    :align: center

Configuring Email Notifications
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

ppagent has the ability to send you an email if your worker meets hits certain
_thresholds_. This is configured per-worker in the ppagent configuration file.

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

The worker name will be automatically pulled from CGMiner, so there's no need
to set it here. To recieve a notification when you're worker goes offline for
at least 5 minute adjust your configuration to look like this:

.. code-block:: json

    [
        {"miner":
            {
                "type": "CGMiner"
                "thresholds": {
                    "offline": 5,
                    "emails": ["winston.com"]
                }
            }
        }
    ]


To detect overheat conditions on any of the cards, simply specify
``"overheat"``. To report low hashrate conditions specify ``"lowhashrate"``
with a number in KH/s. So with the below configuration myself and fred get
notified if my worker is offline for 15 minutes, goes below 2 MH/s, or rises
above 85 C.

.. code-block:: json

    [
        {"miner":
            {
                "type": "CGMiner"
                "thresholds": {
                    "offline": 15,
                    "lowhashrate": 2000,
                    "overheat": 85,
                    "emails": ["winston.com", "fred@simpledoge.com"]
                }
            }
        }
    ]

By default you will also get notified when this condition is resolved (ie card
no longer overheating), however this can be disabled by setting
``"no_green_notif": true``. Also note that a maximum of 6 emails per hour will
be automatically imposed to prevent repeated emailing.

Upgrade
^^^^^^^^^^^^

Ubuntu:

.. code-block:: bash

    sudo pip install --upgrade --ignore-installed ppagent==0.2.6
    sudo service ppagent restart
    # now confirm that the right version is installed
    ppagent --version
    
Debian (for BAMT or SMOS):

.. code-block:: bash

    sudo pip install --upgrade --ignore-installed ppagent==0.2.6
    sudo /etc/init.d/ppagent stop
    sudo /etc/init.d/ppagent start
    # now confirm that the right version is installed
    ppagent --version

Windows:

Simply `Download latest exe <https://github.com/icook/ppagent/releases/download/v0.2.6/ppagent.exe>`_ and replace your old one.

Troubleshooting Upgrade
***************************

On ubuntu, sometimes pip (python package manager) will refuse to install a new
version. Frequently clearing the cache will fix this:

.. code-block:: bash

    sudo rm -rf /tmp/pip-build-root
    
You can also try uninstalling and reinstalling it. This will not
remove you're configuration files.

.. code-block:: bash

    sudo pip uninstall ppagent
    sudo pip install ppagent

If you still can't get it you're welcome to come bug us on `IRC
<https://kiwiirc.com/client/irc.freenode.net/#simpledoge>`_, we're usually on
during the day.
    
Troubleshooting
^^^^^^^^^^^^^^^
If stats aren't showing up after a minute or two you should first check the logs.

On debian these are at:

.. code-block:: bash

    /var/log/ppagent.log
    
On Ubuntu:

.. code-block:: bash

    /var/log/upstart/ppagent.log

On Windows they're in the console that appears when you launch the client.
    
The error messages should give you a clue why it's not working.
If not, login to the `simple doge IRC <https://kiwiirc.com/client/irc.freenode.net/#simpledoge>`_
and we'll try to help you get is straightened out.

Non-Standard Configurations
^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you're not running cgminer on the same computer as ppagent, or you're running on a non-standard port you'll have to tweak the configuration file a little bit.

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
