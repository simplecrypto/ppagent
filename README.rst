PowerPool Agent
===============
A statistics collection agent for the PowerPool mining server. It was built to
work with `Simple Doge mining pool <http://simpledoge.com>`_ . Currently only
available for linux distributions running python 2.6 or 2.7. Tested on cgminer
3.7.2 and sgminer 4.1.0, may work for other cgminer derivatives.

Installation
^^^^^^^^^^^^

Make sure your cgminer or sgminer is running with the api port enabled. This
can be done on command line with the ``--api-allow`` argument, or in your
configuration file with ``"api-allow": true``.

Ubuntu:

.. code-block:: bash

    sudo pip install ppagent
    sudo ppagent install upstart
    
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
