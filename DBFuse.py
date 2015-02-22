#!/usr/bin/python


from __future__ import with_statement

import os
import sys
import errno
import locale
import pwd
from time import time,mktime
from datetime import datetime
from StringIO import StringIO
import stat
import tempfile

# pip install --user fusepy
# pip install --user dropbox
# sudo adduser <username> fuse

# Based off of a template for FUSE available at
# http://www.stavros.io/posts/python-fuse-filesystem/

from fuse import FUSE, FuseOSError, Operations
from dropbox import client, rest, session

def debug(trace=True):
    """a decorator for handling authentication and exceptions"""
    def decorate(f):
        def wrapper(self, *args, **kwargs):
            if trace:
                print "%s called with args " %  f.func_name, args
            return f(self, *args, **kwargs)

        wrapper.__doc__ = f.__doc__
        return wrapper
    return decorate

# The part for obtaining the access token is not yet implemented, but it must
# be done interactively against the developer's server, to protect the
# developer's APP_SECRET and APP_KEY
class DBFuse(Operations):
   def __init__(self):
      try:
        accessToken = open("token_store.txt").read()[len('oauth2:'):]
        self.api_client = client.DropboxClient(accessToken)
        account_info = self.api_client.account_info()
      except:
        print "Please provide an oauth2 token in token_store.txt"
        sys.exit(1)

      # Metadata cache
      self.metadata = {}

      # File handles
      self.fileHandles = {}
      self.pathToHandle = {}
      # Current file number
      self.fileNumber = 1
      print "Mounting %s's Dropbox account." % account_info['display_name']
      print "Account Email Address: %s" % account_info['email']

    # Helper methods
    # ==================
   def getMetadata(self, path):
        CACHE_TIME = 60
        now = time() 
        timeout = now + CACHE_TIME
        if path not in self.metadata or self.metadata[path][0]  < now:
            try:
              meta = self.api_client.metadata(path)
              self.metadata[path] = (timeout, meta)

              # If successful, we should also cache the metadata for all the
              # non-directory entries to avoid additional queries
              if 'contents' in meta:
                for f in meta['contents']:
                  if not f['is_dir']:
                    self.metadata[f['path']] = (timeout, f)
                   
            except:
              self.metadata[path] = (timeout, None)
        return self.metadata[path][1]

   def cleanMeta(self,path):
      try: del self.metadata[path]
      except: pass
      try: self.metadata[os.dirname(path)]
      except: pass

   def moveHelper(self, old, new, func):
      # Check for existence of the old
      self.access(old)
      try:
        func(old,new)
        self.cleanMeta(old)
        self.cleanMeta(new)
      except rest.ErrorResponse as e:
        if e.status == 403:
          raise FuseOSError(errno.EEXIST)
        else:
          print "An unknown error occured at the dropbox end"
          print e
      
   def getHandle(self):
      self.fileNumber += 1
      return self.fileNumber - 1

   def convertToStringIO(self, fh):
     f = self.fileHandles[fh]
     if not isinstance(f, StringIO):
        newF = StringIO(f.read())
        self.fileHandles[fh] = newF
        return newF
     return f


    # Filesystem methods
    # ==================

   # Only possible error is if the path does not exist. 
   def access(self, path, mode=None):
      metadata = self.getMetadata(path)
      if not metadata or 'is_deleted' in  metadata:
        raise FuseOSError(errno.ENOENT)

   # This operation is not supported on Dropbox
   def chmod(self, path, mode):
       pass

   # This operation is not supported on Dropbox
   def chown(self, path, uid, gid):
       pass

   # TODO: Let fuse handle the case where path is not legitimate
   @debug(False)
   def getattr(self, path, fh=None):
       # Get userid and groupid for current user.
       uid = pwd.getpwuid(os.getuid()).pw_uid
       gid = pwd.getpwuid(os.getuid()).pw_gid

       # Get current time.
       now = int(time())

       # Check wether data exists for item.
       path = path.strip()
       item = self.getMetadata(path)

       if not item or 'is_deleted' in item:
         raise FuseOSError(errno.ENOENT)

       # Handle last modified times.
       if 'modified' in item:
         modified = item['modified']
         modified = mktime(datetime.strptime(modified, '%a, %d %b %Y %H:%M:%S +0000').timetuple())
       else:
         modified = int(now)

       if item['is_dir'] == True:
         # Get st_nlink count for directory.
         properties = dict(
           st_mode=stat.S_IFDIR | 0755,
           st_size=0,
           st_ctime=modified,
           st_mtime=modified,
           st_atime=now,
           st_uid=uid,
           st_gid=gid,
           st_nlink=2
         )
         return properties
       properties = dict(
         st_mode=stat.S_IFREG | 0755,
         st_size=item['bytes'],
         st_ctime=modified,
         st_mtime=modified,
         st_atime=now,
         st_uid=uid,
         st_gid=gid,
         st_nlink=1,
       )
       return properties

              

   @debug()
   def readdir(self, path, fh):
       dirents = ['.', '..']
       resp = self.getMetadata(path)
       if resp and 'contents' in resp:
           for f in resp['contents']:
               name = os.path.basename(f['path'])
               encoding = locale.getdefaultlocale()[1] or 'ascii'
               dirents.append(('%s' % name).encode(encoding))
       for r in dirents:
           yield r

   # Dropbox does not support symlinks
   @debug()
   def readlink(self, path):
        raise FuseOSError(errno.EPERM)

   # Only supported for creating files and directories
   @debug()
   def mknod(self, path, mode, dev=None):
      if mode  != stat.S_IFREG:
        raise FuseOSError(errno.EPERM)
      # Default to creating a file of empty length by faking it with an empty stringIO
      self.api_client.put_file(path, StringIO())
      self.cleanMeta(path)
        
   @debug()
   def rmdir(self, path):
      metadata = self.getMetadata(path)
      if not metadata:
        raise FuseOSError(errno.ENOENT)
      if not metadata['is_dir']:
        raise FuseOSError(errno.ENOTDIR)
      if 'contents' in metadata and len(metadata['contents']) > 0:
        raise FuseOSError(errono.ENOTEMPTY) 
      try:
        self.api_client.file_delete(path)
        self.cleanMeta(path)
      except Exception as e:
        print "Deletion of directory %s failed!" % path
        print e
        raise FuseOSError(errno.EIO) 


   # If we succeed in creating, we must invalidate the cached value
   @debug()
   def mkdir(self, path, mode):
      try:
        self.api_client.file_create_folder(path)
        self.cleanMeta(path)
      except rest.ErrorResponse as e:
        if e.status == 403:
          raise FuseOSError(errno.EEXIST)
        else:
          print "An unknown error occured at the dropbox end"
################################################################################

#   def statfs(self, path):
#       full_path = self._full_path(path)
#       stv = os.statvfs(full_path)
#       return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
#           'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
#           'f_frsize', 'f_namemax'))

   @debug()
   def unlink(self, path):
      metadata = self.getMetadata(path)
      if not metadata:
        raise FuseOSError(errno.ENOENT)
      if metadata['is_dir']:
        raise FuseOSError(errno.EISDIR)
      try:
        self.api_client.file_delete(path)
        self.cleanMeta(path)
      except:
        print "Deletion of file %s failed!" % path
        raise FuseOSError(errno.EIO) 
      
    
   # Dropbox does not support symlinks
   @debug()
   def symlink(self, name, target):
        raise FuseOSError(errno.EPERM)

   @debug()
   def rename(self, old, new):
      self.moveHelper(old,new, lambda old,new: self.api_client.file_move(old,new))

   # Fuse's get_attr interfaces makes ln fail, so it makes little sense to implement this.
   @debug()
   def link(self, target, name):
      raise FuseOSError(errno.EPERM) 
        
   # Dropbox does not support Updating timestamps only
   @debug()
   def utimens(self, path, times=None):
       pass

   # File methods
   # ============

   @debug()
   def open(self, path, flags=None):
       try:
           f = self.api_client.get_file(path)
           handle = self.getHandle()
           self.pathToHandle[path] = handle
           self.fileHandles[handle] = f
           return handle
       except:
         if flags & os.O_CREAT or flags & os.O_TRUNC or flags & os.O_RDWR or flags & os.O_WRONLY:
           handle = self.getHandle()
           self.pathToHandle[path] = handle
           self.fileHandles[handle] = StringIO()
           return handle

         # Raise only if we have no option to create a file
         raise FuseOSError(errno.ENOENT)

   # If it is not in fileHandles, then it is not legit
   @debug()
   def create(self, path, mode = None, fi=None):
       metadata = self.getMetadata(path)

       # Make sure file does not exist already
       if metadata and not 'is_deleted' in metadata:
          raise FuseOSError(errno.EEXIST)
      
       # Register the new file internally so that get_attr will return something for it
       self.mknod(path, stat.S_IFREG)

       handle = self.getHandle()
       self.pathToHandle[path] = handle
       self.fileHandles[handle] = StringIO()
       return handle
       

      
   # We deliberately do not check if the file still exists, because by normal
   # read semantics, the file exists if you have already opened it
   # TODO: Decide on the correct error to throw if its not there
   @debug()
   def read(self, path, length, offset, fh):
       if fh not in self.fileHandles: raise FuseOSError(errno.EINVAL)
       f = self.convertToStringIO(fh)
       f.seek(offset)
       return f.read(length)

   @debug()
   def write(self, path, buf, offset, fh):
       if fh not in self.fileHandles: raise FuseOSError(errno.EINVAL)
       # Need to convert this into a StringIO if it is not already
       f = self.convertToStringIO(fh)
       f.seek(offset)
       f.write(buf)
       return len(buf)

   @debug()
   def truncate(self, path, length, fh=None):
       if not fh: fh = self.pathToHandle[path]
       if not fh: fh = self.open(path)
       f = self.convertToStringIO(fh)
       return f.truncate(length)

   # Force the data up to Dropbox
   @debug()
   def flush(self, path, fh):
      # First push it to a temporary file, since the API likes to be able to do
      # real file operations
      with tempfile.TemporaryFile() as TFile:
          if isinstance(self.fileHandles[fh], StringIO):
              TFile.write(self.fileHandles[fh].getvalue())
          else:
              f = self.convertToStringIO(fh)
              TFile.write(f.getvalue())
          TFile.seek(0)
          self.api_client.put_file(path, TFile, overwrite=True)
      self.cleanMeta(path)
      return 0
       

   # Clean up state
   @debug()
   def release(self, path, fh):
     try:
        self.fileHandles[fh].close()
        del self.fileHandles[fh]
        del self.pathToHandle[path]
     except:
       print "Error occurred when releasing a file handle"
     return 0

   def fsync(self, path, fdatasync, fh):
       return self.flush(path, fh)

def usage():
   usageMsg = """
   python DBFuse.py <MountPoint>
   """.strip()
   print usageMsg
   sys.exit(1)

def main(mountpoint):
    FUSE(DBFuse(), mountpoint, foreground=True)

if __name__ == '__main__':
    if len(sys.argv) < 2: usage() 
    main(sys.argv[1])
