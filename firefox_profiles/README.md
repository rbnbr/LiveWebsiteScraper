# Firefox Profiles
Opening websocket connections from a https website requires the usage of the wss protocol.
Therefore, you either will have to accept unknown certificates or install the root certificate which was used to sign your websocket server certificate used by your websocket server that receives the data from your local client.
You can do this by providing a firefox profile which has the root certificate in it to authorize the websockets server certificate.

## Create profile locally

1. Open firefox and go to ``about:profiles``.
2. Create a new profile and click ``Profil zusätzlich ausführen`` to run it in a new browser session.
3. Navigate in this browser session to the settings and load the CA certificate as authority.
4. Close the session and select the previous profile as default profile.
5. Copy the profile dir in this directory and name it according to the pyapps ``PYAPP_FIREFOX_PROFILE_DIR`` environment variable, which is by default ``ff-profile.WithCACertificate``.
   It should always start with ``ff-profile.`` to be excluded by ``.gitignore``.
6. Rebuild the container to copy the new profile in the ``/pyapp/firefox_profiles/`` directory, or mount the directory directly in the container.
