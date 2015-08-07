# -*- coding: utf-8 -*-
'''
Support for the Git SCM
'''
from __future__ import absolute_import

# Import python libs
import os
import shlex

# Import salt libs
import salt.utils
from salt.exceptions import SaltInvocationError, CommandExecutionError
from salt.ext import six
from salt.ext.six.moves.urllib.parse import urlparse as _urlparse  # pylint: disable=no-name-in-module,import-error
from salt.ext.six.moves.urllib.parse import urlunparse as _urlunparse  # pylint: disable=no-name-in-module,import-error


def __virtual__():
    '''
    Only load if git exists on the system
    '''
    return True if salt.utils.which('git') else False


def _git_run(command, cwd=None, runas=None, identity=None,
             ignore_retcode=False, **kwargs):
    '''
    simple, throw an exception with the error message on an error return code.

    this function may be moved to the command module, spliced with
    'cmd.run_all', and used as an alternative to 'cmd.run_all'. Some
    commands don't return proper retcodes, so this can't replace 'cmd.run_all'.
    '''
    env = {}

    if identity:
        stderrs = []

        # if the statefile provides multiple identities, they need to be tried
        # (but also allow a string instead of a list)
        if not isinstance(identity, list):
            # force it into a list
            identity = [identity]

        # try each of the identities, independently
        for id_file in identity:
            env = {
                'GIT_IDENTITY': id_file
            }

            # copy wrapper to area accessible by ``runas`` user
            # currently no suppport in windows for wrapping git ssh
            if not utils.is_windows():
                ssh_id_wrapper = os.path.join(utils.templates.TEMPLATE_DIRNAME,
                                              'git/ssh-id-wrapper')
                tmp_file = utils.mkstemp()
                utils.files.copyfile(ssh_id_wrapper, tmp_file)
                os.chmod(tmp_file, 0o500)
                os.chown(tmp_file, __salt__['file.user_to_uid'](runas), -1)
                env['GIT_SSH'] = tmp_file

            try:
                result = __salt__['cmd.run_all'](command,
                                                 cwd=cwd,
                                                 runas=runas,
                                                 env=env,
                                                 python_shell=False,
                                                 ignore_retcode=ignore_retcode,
                                                 **kwargs)
            finally:
                if 'GIT_SSH' in env:
                    os.remove(env['GIT_SSH'])

            # if the command was successful, no need to try additional IDs
            if result['retcode'] == 0:
                return result
            else:
                stderrs.append(result['stderr'])

        # we've tried all IDs and still haven't passed, so error out
        raise CommandExecutionError("\n\n".join(stderrs))

    else:
        result = __salt__['cmd.run_all'](command,
                                         cwd=cwd,
                                         runas=runas,
                                         env=env,
                                         python_shell=False,
                                         ignore_retcode=ignore_retcode,
                                         **kwargs)
        retcode = result['retcode']

        if retcode == 0:
            return result
        else:
            msg = 'Command \'{0}\' failed'.format(command)
            if result['stderr']:
                msg += ': {0}'.format(result['stderr'])
            raise CommandExecutionError(msg)


def _check_abs(*paths):
    '''
    Ensure that the path is absolute
    '''
    for path in paths:
        if not isinstance(path, six.string_types) or not os.path.isabs(path):
            raise SaltInvocationError(
                'Path \'{0}\' is not absolute'.format(path)
            )


def _format_opts(opts):
    '''
    Common code to inspect opts and split them if necessary
    '''
    if opts is None:
        return []
    elif isinstance(opts, list):
        if any(x for x in opts if not isinstance(x, six.string_types)):
            return [str(x) for x in opts]
        if opts[-1] == '--':
            # Strip the '--' if it was passed at the end of the opts string,
            # it'll be added back (if necessary) in the calling function.
            # Putting this check here keeps it from having to be repeated every
            # time _format_opts() is invoked.
            return opts[:-1]
        return opts
    else:
        if not isinstance(opts, six.string_types):
            return [str(opts)]
        return shlex.split(opts)


def _add_http_basic_auth(url, https_user=None, https_pass=None):
    if https_user is None and https_pass is None:
        return url
    else:
        urltuple = _urlparse(url)
        if urltuple.scheme == 'https':
            netloc = '{0}:{1}@{2}'.format(
                https_user,
                https_pass,
                urltuple.netloc
            )
            urltuple = urltuple._replace(netloc=netloc)
            return _urlunparse(urltuple)
        else:
            raise SaltInvocationError('Basic Auth only supported for HTTPS')


def _get_toplevel(path, user=None):
    '''
    Use git rev-parse to return the top level of a repo
    '''
    return _git_run(
        ['git', 'rev-parse', '--show-toplevel'],
        cwd=path,
        runas=user
    )['stdout']


def current_branch(cwd, user=None, ignore_retcode=False):
    '''
    Returns the current branch name of a local checkout. If HEAD is detached,
    return the SHA1 of the revision which is currently checked out.

    cwd
        The path to the git checkout

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Example:

    .. code-block:: bash

        salt myminion git.current_branch /path/to/repo
    '''
    _check_abs(cwd)
    command = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def revision(cwd, rev='HEAD', short=False, user=None, ignore_retcode=False):
    '''
    Returns the SHA1 hash of a given identifier (hash, branch, tag, HEAD, etc.)

    cwd
        The path to the git checkout

    rev : HEAD
        The revision

    short : False
        If ``True``, return an abbreviated SHA1 git hash

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    CLI Example:

    .. code-block:: bash

        salt myminion git.revision /path/to/repo mybranch
    '''
    _check_abs(cwd)
    if not isinstance(rev, six.string_types):
        rev = str(rev)
    command = ['git', 'rev-parse']
    if short:
        command.append('--short')
    command.append(rev)
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def clone(cwd,
          url=None,  # Remove default value once 'repository' arg is removed
          opts='',
          user=None,
          identity=None,
          https_user=None,
          https_pass=None,
          ignore_retcode=False,
          repository=None):
    '''
    Interface to `git-clone(1)`_

    cwd
        The path to the git checkout

    url
        The URL of the repository to be cloned

        .. versionchanged:: 2015.8.0
            Argument renamed from ``repository`` to ``url``

    opts
        Any additional options to add to the command line, in a single string

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

        Run git as a user other than what the minion runs as

    identity
        Path to a private key to use for ssh URLs

        .. warning::

            Key must be passphraseless to allow for non-interactive login. For
            greater security with passphraseless private keys, see the
            `sshd(8)`_ manpage for information on securing the keypair from the
            remote side in the ``authorized_keys`` file.

            .. _`sshd(8)`: http://www.man7.org/linux/man-pages/man8/sshd.8.html#AUTHORIZED_KEYS_FILE%20FORMAT

    https_user
        Set HTTP Basic Auth username. Only accepted for HTTPS URLs.

        .. versionadded:: 20515.5.0

    https_pass
        Set HTTP Basic Auth password. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.5.0

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-clone(1)`: http://git-scm.com/docs/git-clone

    CLI Example:

    .. code-block:: bash

        salt myminion git.clone /path/to/repo git://github.com/saltstack/salt.git
    '''
    _check_abs(cwd)
    if repository is not None:
        salt.utils.warn_until(
            'Nitrogen',
            'The \'repository\' argument to git.clone has been '
            'deprecated, please use \'url\' instead.'
        )
        url = repository

    if not url:
        raise SaltInvocationError('Missing \'url\' argument')

    url = _add_http_basic_auth(url, https_user, https_pass)
    command = ['git', 'clone', url, cwd]
    command.extend(_format_opts(opts))
    return _git_run(command,
                    runas=user,
                    identity=identity,
                    ignore_retcode=ignore_retcode)['stdout']


def describe(cwd, rev='HEAD', user=None, ignore_retcode=False):
    '''
    Returns the `git-describe(1)`_ string (or the SHA1 hash if there are no
    tags) for the given revision.

    cwd
        The path to the git checkout

    rev : HEAD
        The revision to describe

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-describe(1)`: http://git-scm.com/docs/git-describe


    CLI Examples:

    .. code-block:: bash

        salt myminion git.describe /path/to/repo
        salt myminion git.describe /path/to/repo develop
    '''
    _check_abs(cwd)
    if not isinstance(rev, six.string_types):
        rev = str(rev)
    command = ['git', 'describe', rev]
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def archive(cwd,
            output,
            rev='HEAD',
            fmt=None,
            prefix=None,
            user=None,
            ignore_retcode=False,
            **kwargs):
    '''
    .. versionchanged:: 2015.8.0
        Returns ``True`` if successful, raises an error if not.

    Interface to `git-archive(1)`_, exports a tarball/zip file of the
    repository

    cwd
        The path to be archived

        .. note::
            ``git archive`` permits a partial archive to be created. Thus, this
            path does not need to be the root of the git repository. Only the
            files within the directory specified by ``cwd`` (and its
            subdirectories) will be in the resulting archive. For example, if
            there is a git checkout at ``/tmp/foo``, then passing
            ``/tmp/foo/bar`` as the ``cwd`` will result in just the files
            underneath ``/tmp/foo/bar`` to be exported as an archive.

    output
        The path of the archive to be created

    overwrite : False
        Unless set to ``True``, Salt will over overwrite an existing archive at
        the path specified by the ``output`` argument.

        .. versionadded:: 2015.8.0

    rev : HEAD
        The revision from which to create the archive

    format
        Manually specify the file format of the resulting archive. This
        argument can be omitted, and ``git archive`` will attempt to guess the
        archive type (and compression) from the filename. ``zip``, ``tar``,
        ``tar.gz``, and ``tgz`` are extensions that are recognized
        automatically, and git can be configured to support other archive types
        with the addition of git configuration keys.

        See the `git-archive(1)`_ manpage explanation of the
        ``--format`` argument (as well as the ``CONFIGURATION`` section of the
        manpage) for further information.

        .. versionadded:: 2015.8.0

    fmt
        Replaced by ``format`` in version 2015.8.0

        .. deprecated:: 2015.8.0

    prefix
        Prepend ``<prefix>`` to every filename in the archive. If unspecified,
        the name of the directory at the top level of the repository will be
        used as the prefix (e.g. if ``cwd`` is set to ``/foo/bar/baz``, the
        prefix will be ``baz``, and the resulting archive will contain a
        top-level directory by that name).

        .. note::
            The default behavior if the ``--prefix`` option for ``git archive``
            is not specified is to not prepend a prefix, so Salt's behavior
            differs slightly from ``git archive`` in this respect. Use
            ``prefix=''`` to create an archive with no prefix.

        .. versionchanged:: 2015.8.0
            The behavior of this argument has been changed slightly. As of
            this version, it is necessary to include the trailing slash when
            specifying a prefix, if the prefix is intended to create a
            top-level directory.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-archive(1)`: http://git-scm.com/docs/git-archive


    CLI Example:

    .. code-block:: bash

        salt myminion git.archive /path/to/repo /path/to/archive.tar
    '''
    _check_abs(cwd, output)
    # Sanitize kwargs and make sure that no invalid ones were passed. This
    # allows us to accept 'format' as an argument to this function without
    # shadowing the format() global, while also not allowing unwanted arguments
    # to be passed.
    kwargs = salt.utils.clean_kwargs(**kwargs)
    format_ = kwargs.pop('format', None)
    if kwargs:
        raise SaltInvocationError(
            'The following keyword arguments are invalid: {0}'.format(
                ', '.join([
                    '{0}={1}'.format(key, val)
                    for key, val in six.iteritems(kwargs)
                ])
            )
        )

    if fmt:
        salt.utils.warn_until(
            'Nitrogen',
            'The \'fmt\' argument to git.archive has been deprecated, please '
            'use \'format\' instead.'
        )
        format_ = fmt

    command = ['git', 'archive']
    # If prefix was set to '' then we skip adding the --prefix option
    if prefix != '':
        if prefix:
            if not isinstance(prefix, six.string_types):
                prefix = str(prefix)
        else:
            prefix = os.path.basename(cwd)
        command.extend(['--prefix', prefix])

    if format_:
        if not isinstance(format_, six.string_types):
            format_ = str(format_)
        command.extend(['--format', format_])
    command.extend(['--output', output, rev])
    _git_run(command, cwd=cwd, runas=user, ignore_retcode=ignore_retcode)
    # No output (unless --verbose is used, and we don't want all files listed
    # in the output in case there are thousands), so just return True
    return True


def fetch(cwd,
          remote=None,
          opts='',
          user=None,
          identity=None,
          ignore_retcode=False):
    '''
    Interface to `git-fetch(1)`_

    cwd
        The path to the git checkout

    remote
        Optional remote name to fetch. If not passed, then git will use its
        default behavior (as detailed in `git-fetch(1)`_).

        .. versionadded:: 2015.8.0

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    identity
        Path to a private key to use for ssh URLs

        .. warning::

            Key must be passphraseless to allow for non-interactive login. For
            greater security with passphraseless private keys, see the
            `sshd(8)`_ manpage for information on securing the keypair from the
            remote side in the ``authorized_keys`` file.

            .. _`sshd(8)`: http://www.man7.org/linux/man-pages/man8/sshd.8.html#AUTHORIZED_KEYS_FILE%20FORMAT

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-fetch(1)`: http://git-scm.com/docs/git-fetch


    CLI Example:

    .. code-block:: bash

        salt myminion git.fetch /path/to/repo upstream
        salt myminion git.fetch /path/to/repo identity=/root/.ssh/id_rsa
    '''
    _check_abs(cwd)
    command = ['git', 'fetch']
    if not isinstance(remote, six.string_types):
        remote = str(remote)
    if remote:
        command.append(remote)
    command.extend(format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    identity=identity,
                    ignore_retcode=ignore_retcode)['stdout']


def pull(cwd, opts='', user=None, identity=None, ignore_retcode=False):
    '''
    Interface to `git-pull(1)`_

    cwd
        The path to the git checkout

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    identity
        Path to a private key to use for ssh URLs

        .. warning::

            Key must be passphraseless to allow for non-interactive login. For
            greater security with passphraseless private keys, see the
            `sshd(8)`_ manpage for information on securing the keypair from the
            remote side in the ``authorized_keys`` file.

            .. _`sshd(8)`: http://www.man7.org/linux/man-pages/man8/sshd.8.html#AUTHORIZED_KEYS_FILE%20FORMAT

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-pull(1)`: http://git-scm.com/docs/git-pull

    CLI Example:

    .. code-block:: bash

        salt myminion git.pull /path/to/repo opts='--rebase origin master'
    '''
    _check_abs(cwd)
    command = ['git', 'pull']
    command.extend(_format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    identity=identity,
                    ignore_retcode=ignore_retcode)['stdout']


def rebase(cwd, rev='master', opts='', user=None, ignore_retcode=False):
    '''
    Interface to `git-rebase(1)`_

    cwd
        The path to the git checkout

    rev : master
        The revision to rebase onto the current branch

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-rebase(1)`: http://git-scm.com/docs/git-rebase


    CLI Example:

    .. code-block:: bash

        salt myminion git.rebase /path/to/repo master
        salt myminion git.rebase /path/to/repo 'origin master'
        salt myminion git.rebase /path/to/repo origin/master opts='--onto newbranch'
    '''
    _check_abs(cwd)
    command = ['git', 'rebase']
    command.extend(_format_opts(opts))
    if not isinstance(rev, six.string_types):
        rev = str(rev)
    command.extend(shlex.split(rev))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def checkout(cwd, rev, force=False, opts='', user=None, ignore_retcode=False):
    '''
    Interface to `git-checkout(1)`_

    cwd
        The path to the git checkout

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    rev
        The remote branch or revision to checkout

    force : False
        Force a checkout even if there might be overwritten changes

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-checkout(1)`: http://git-scm.com/docs/git-checkout


    CLI Examples:

    .. code-block:: bash

        # Checking out local local revisions
        salt myminion git.checkout /path/to/repo somebranch user=jeff
        salt myminion git.checkout /path/to/repo opts='testbranch -- conf/file1 file2'
        salt myminion git.checkout /path/to/repo rev=origin/mybranch opts='--track'
        # Checking out remote revision into new branch
        salt myminion git.checkout /path/to/repo upstream/master opts='-b newbranch'
    '''
    _check_abs(cwd)
    command = ['git', 'checkout']
    if force:
        command.append('--force')
    if not isinstance(rev, six.string_types):
        rev = str(rev)
    command.extend(shlex.split(rev))
    command.extend(_format_opts(opts))
    # Checkout message goes to stderr
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stderr']


def merge(cwd,
          rev=None,
          opts='',
          user=None,
          branch=None,
          ignore_retcode=False):
    '''
    Interface to `git-merge(1)`_

    cwd
        The path to the git checkout

    rev
        Revision to merge into the current branch. If not specified, the remote
        tracking branch will be merged.

        .. versionadded:: 2015.8.0

    branch
        The remote branch or revision to merge into the current branch
        Revision to merge into the current branch

        .. versionchanged:: 2015.8.0
            Default value changed from ``'@{upstream}'`` to ``None`` (unset),
            allowing this function to merge the remote tracking branch without
            having to specify it

        .. deprecated:: 2015.8.0
            Use ``rev`` instead.

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-merge(1)`: http://git-scm.com/docs/git-merge


    CLI Example:

    .. code-block:: bash

        # Fetch first...
        salt myminion git.fetch /path/to/repo
        # ... then merge the remote tracking branch
        salt myminion git.merge /path/to/repo
        # .. or merge another rev
        salt myminion git.merge /path/to/repo rev=upstream/foo
    '''
    _check_abs(cwd)
    if branch:
        salt.utils.warn_until(
            'Nitrogen',
            'The \'branch\' argument to git.merge has been deprecated, please '
            'use \'rev\' instead.'
        )
        rev = branch
    command = ['git', 'merge']
    if rev:
        if not isinstance(rev, six.string_types):
            rev = str(rev)
        command.append(rev)
    command.extend(_format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def init(cwd,
         bare=False,
         template=None,
         separate_git_dir=None,
         shared=None,
         opts='',
         user=None,
         ignore_retcode=False):
    '''
    Interface to `git-init(1)`_

    cwd
        The path to the directory to be initialized

    bare : False
        If ``True``, init a bare repository

        .. versionadded:: 2015.8.0

    template
        Set this argument to specify an alternate `template directory`_

        .. versionadded:: 2015.8.0

    separate_git_dir
        Set this argument to specify an alternate ``$GIT_DIR``

        .. versionadded:: 2015.8.0

    shared
        Set sharing permissions on git repo. See `git-init(1)`_ for more
        details.

        .. versionadded:: 2015.8.0

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-init(1)`: http://git-scm.com/docs/git-init
    .. _`template directory`: http://git-scm.com/docs/git-init#_template_directory


    CLI Examples:

    .. code-block:: bash

        salt myminion git.init /path/to/repo
        # Init a bare repo (before 2015.8.0)
        salt myminion git.init /path/to/bare/repo.git opts='--bare'
        # Init a bare repo (2015.8.0 and later)
        salt myminion git.init /path/to/bare/repo.git bare=True
    '''
    _check_abs(cwd)
    command = ['git', 'init']
    if bare:
        command.append('--bare')
    if template is not None:
        if not isinstance(template, six.string_types):
            template = str(template)
        command.extend(['--template', template])
    if separate_git_dir is not None:
        if not isinstance(separate_git_dir, six.string_types):
            separate_git_dir = str(separate_git_dir)
        command.extend(['--separate-git-dir', separate_git_dir])
    if shared is not None:
        if isinstance(shared, six.integer_types):
            shared = '0' + str(shared)
        elif not isinstance(shared, six.string_types):
            # Using lower here because booleans would be capitalized when
            # converted to a string.
            shared = str(shared).lower()
        command.extend(['--shared', shared])
    command.extend(_format_opts(opts))
    command.append(cwd)
    return _git_run(command,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def submodule(cwd,
              command,
              opts='',
              user=None,
              identity=None,
              init=False,
              ignore_retcode=False):
    '''
    .. versionchanged:: 2015.8.0
        Added the ``command`` argument to allow for operations other than
        ``update`` to be run on submodules, and deprecated the ``init``
        argument. To do a submodule update with ``init=True`` moving forward,
        use ``command=update opts='--init'``

    Interface to `git-submodule(1)`_

    cwd
        The path to the submodule

    command
        Submodule command to run, see `git-submodule(1) <git submodule>` for
        more information. Any additional arguments after the command (such as
        the URL when adding a submodule) must be passed in the ``opts``
        parameter.

        .. versionadded:: 2015.8.0

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    init : False
        If ``True``, ensures that new submodules are initialized

        .. deprecated:: 2015.8.0
            Pass ``init`` as the ``command`` parameter, or include ``--init``
            in the ``opts`` param with ``command`` set to update.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    identity
        Path to a private key to use for ssh URLs

        .. warning::

            Key must be passphraseless to allow for non-interactive login. For
            greater security with passphraseless private keys, see the
            `sshd(8)`_ manpage for information on securing the keypair from the
            remote side in the ``authorized_keys`` file.

            .. _`sshd(8)`: http://www.man7.org/linux/man-pages/man8/sshd.8.html#AUTHORIZED_KEYS_FILE%20FORMAT

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-submodule(1)`: http://git-scm.com/docs/git-submodule

    CLI Example:

    .. code-block:: bash

        # Update submodule and ensure it is initialized (before 2015.8.0)
        salt myminion git.submodule /path/to/repo/sub/repo init=True
        # Update submodule and ensure it is initialized (2015.8.0 and later)
        salt myminion git.submodule /path/to/repo/sub/repo update opts='--init'

        # Rebase submodule (2015.8.0 and later)
        salt myminion git.submodule /path/to/repo/sub/repo update opts='--rebase'

        # Add submodule (2015.8.0 and later)
        salt myminion git.submodule /path/to/repo/sub/repo add opts='https://mydomain.tld/repo.git'

        # Unregister submodule (2015.8.0 and later)
        salt myminion git.submodule /path/to/repo/sub/repo deinit
    '''
    _check_abs(cwd)
    if init:
        raise SaltInvocationError(
            'The \'init\' argument is no longer supported. Either set '
            '\'command\' to \'init\', or include \'--init\' in the \'opts\' '
            'argument and set \'command\' to \'update\'.'
        )
    if not isinstance(command, six.string_types):
        command = str(command)
    command = ['git', 'submodule', command]
    command.extend(_format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    identity=identity,
                    ignore_retcode=ignore_retcode)['stdout']


def status(cwd, user=None, ignore_retcode=False):
    '''
    .. versionchanged:: 2015.8.0
        Return data has changed from a list of tuples to a dictionary

    Returns the changes to the repository

    cwd
        The path to the git checkout

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Example:

    .. code-block:: bash

        salt myminion git.status /path/to/repo
    '''
    _check_abs(cwd)
    state_map = {
        'M': 'modified',
        'A': 'new',
        'D': 'deleted',
        '??': 'untracked'
    }
    ret = {}
    command = ['git', 'status', '-z', '--porcelain']
    output = _git_run(command,
                      cwd=cwd,
                      runas=user,
                      ignore_retcode=ignore_retcode)['stdout']
    for line in output.split('\0'):
        try:
            state, filename = line.split(None, 1)
        except ValueError:
            continue
        ret.setdefault(state_map.get(state, state), []).append(filename)
    return ret


def add(cwd, filename, opts='', user=None, ignore_retcode=False):
    '''
    .. versionchanged:: 2015.8.0
        The ``--verbose`` command line argument is now implied

    Interface to `git-add(1)`_

    cwd
        The path to the git checkout

    filename
        The location of the file/directory to add, relative to ``cwd``

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-add(1)`: http://git-scm.com/docs/git-add


    CLI Examples:

    .. code-block:: bash

        salt myminion git.add /path/to/repo foo/bar.py
        salt myminion git.add /path/to/repo foo/bar.py opts='--dry-run'
    '''
    _check_abs(cwd)
    if not isinstance(filename, six.string_types):
        filename = str(filename)
    command = ['git', 'add', '--verbose']
    command.extend(
        [x for x in _format_opts(opts) if x not in ('-v', '--verbose')]
    )
    command.extend(['--', filename])
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def rm(cwd, filename, opts='', user=None, ignore_retcode=False):
    '''
    Interface to `git-rm(1)`_

    cwd
        The path to the git checkout

    filename
        The location of the file/directory to remove, relative to ``cwd``

        .. note::
            To remove a directory, ``-r`` must be part of the ``opts``
            parameter.

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-rm(1)`: http://git-scm.com/docs/git-rm


    CLI Examples:

    .. code-block:: bash

        salt myminion git.rm /path/to/repo foo/bar.py
        salt myminion git.rm /path/to/repo foo/bar.py opts='--dry-run'
        salt myminion git.rm /path/to/repo foo/baz opts='-r'
    '''
    _check_abs(cwd)
    command = ['git', 'rm']
    command.extend(_format_opts(opts))
    command.extend(['--', filename])
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def commit(cwd,
           message,
           opts='',
           user=None,
           filename=None,
           ignore_retcode=False):
    '''
    Interface to `git-commit(1)`_

    cwd
        The path to the git checkout

    message
        Commit message

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

            The ``-m`` option should not be passed here, as the commit message
            will be defined by the ``message`` argument.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    filename
        The location of the file/directory to commit, relative to ``cwd``.
        This argument is optional, and can be used to commit a file without
        first staging it.

        .. versionadded:: 2015.8.0

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-commit(1)`: http://git-scm.com/docs/git-commit


    CLI Examples:

    .. code-block:: bash

        salt myminion git.commit /path/to/repo 'The commit message'
        salt myminion git.commit /path/to/repo 'The commit message' filename=foo/bar.py
    '''
    _check_abs(cwd)
    command = ['git', 'commit', '-m', message]
    command.extend(_format_opts(opts))
    if filename:
        if not isinstance(filename, six.string_types):
            filename = str(filename)
        # Add the '--' to terminate CLI args, but only if it wasn't already
        # passed in opts string.
        command.extend(['--', filename])
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def push(cwd,
         remote=None,
         ref=None,
         opts='',
         user=None,
         identity=None,
         ignore_retcode=False,
         branch=None):
    '''
    .. versionchanged:: 2015.8.0

    Interface to `git-push(1)`_

    cwd
        The path to the git checkout

    remote
        Name of the remote to which the ref should being pushed

        .. versionadded:: 2015.8.0

    ref : master
        Name of the ref to push

        .. note::
            Being a refspec_, this argument can include a colon to define local
            and remote ref names.

    branch
        Name of the ref to push

        .. deprecated:: 2015.8.0
            Use ``ref`` instead

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    identity
        Path to a private key to use for ssh URLs

        .. warning::

            Key must be passphraseless to allow for non-interactive login. For
            greater security with passphraseless private keys, see the
            `sshd(8)`_ manpage for information on securing the keypair from the
            remote side in the ``authorized_keys`` file.

            .. _`sshd(8)`: http://www.man7.org/linux/man-pages/man8/sshd.8.html#AUTHORIZED_KEYS_FILE%20FORMAT

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-push(1)`: http://git-scm.com/docs/git-push
    .. _refspec: http://git-scm.com/book/en/v2/Git-Internals-The-Refspec

    CLI Example:

    .. code-block:: bash

        # Push master as origin/master
        salt myminion git.push /path/to/repo origin master
        # Push issue21 as upstream/develop
        salt myminion git.push /path/to/repo upstream issue21:develop
        # Delete remote branch 'upstream/temp'
        salt myminion git.push /path/to/repo upstream :temp
    '''
    _check_abs(cwd)
    if branch:
        salt.utils.warn_until(
            'Nitrogen',
            'The \'branch\' argument to git.push has been deprecated, please '
            'use \'ref\' instead.'
        )
        ref = branch
    command = ['git', 'push']
    command.extend(_format_opts(opts))
    if not isinstance(remote, six.string_types):
        remote = str(remote)
    if not isinstance(ref, six.string_types):
        ref = str(ref)
    command.extend([remote, ref])
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    identity=identity,
                    ignore_retcode=ignore_retcode)['stdout']


def remotes(cwd, user=None, ignore_retcode=False):
    '''
    Get fetch and push URLs for each remote in a git checkout

    cwd
        The path to the git checkout

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Example:

    .. code-block:: bash

        salt myminion git.remotes /path/to/repo
    '''
    _check_abs(cwd)
    command = ['git', 'remote', '--verbose']
    ret = {}
    output = _git_run(command,
                      cwd=cwd,
                      runas=user,
                      ignore_retcode=ignore_retcode)['stdout']
    for remote_line in output.splitlines():
        try:
            remote, remote_info = remote_line.split(None, 1)
        except ValueError:
            continue
        try:
            remote_url, action = remote_info.rsplit(None, 1)
        except ValueError:
            continue
        # Remove parenthesis
        action = action.lstrip('(').rstrip(')').lower()
        if action not in ('fetch', 'push'):
            log.warning(
                'Unknown action \'{0}\' for remote \'{1}\' in git checkout '
                'located in {2}'.format(action, remote, cwd)
            )
            continue
        ret.setdefault(remote, {})[action] = remote_url
    return ret


def remote_get(cwd, remote='origin', user=None, ignore_retcode=False):
    '''
    Get the fetch and push URL for a specific remote

    cwd
        The path to the git checkout

    remote : origin
        Name of the remote to query

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    CLI Example:

    .. code-block:: bash

        salt myminion git.remote_get /path/to/repo
        salt myminion git.remote_get /path/to/repo upstream
    '''
    _check_abs(cwd)
    all_remotes = remotes(cwd, user=user, ignore_retcode=ignore_retcode)
    if remote not in all_remotes:
        raise CommandExecutionError(
            'Remote \'{0}\' not present in git checkout located at {1}'
            .format(remote, cwd)
        )
    return all_remotes[remote]


def remote_set(cwd,
               url,
               remote='origin',
               user=None,
               https_user=None,
               https_pass=None,
               push_url=None,
               push_https_user=None,
               push_https_pass=None,
               ignore_retcode=False):
    '''
    cwd
        The path to the git checkout

    url
        Remote URL to set

    remote : origin
        Name of the remote to set

    push_url
        If unset, the push URL will be identical to the fetch URL.

        .. versionadded:: 2015.8.0

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    https_user
        Set HTTP Basic Auth username. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.5.0

    https_pass
        Set HTTP Basic Auth password. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.5.0

    push_https_user
        Set HTTP Basic Auth user for ``push_url``. Ignored if ``push_url`` is
        unset. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.8.0

    push_https_pass
        Set HTTP Basic Auth password for ``push_url``. Ignored if ``push_url``
        is unset. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.8.0

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Examples:

    .. code-block:: bash

        salt myminion git.remote_set /path/to/repo git@github.com:user/repo.git
        salt myminion git.remote_set /path/to/repo git@github.com:user/repo.git remote=upstream
        salt myminion git.remote_set /path/to/repo https://github.com/user/repo.git remote=upstream push_url=git@github.com:user/repo.git
    '''
    # Check if remote exists
    if remote not in remotes(cwd, user=user, ignore_retcode=ignore_retcode):
        log.debug(
            'Remote \'{0}\' already exists in git checkout located at {1}, '
            'removing so it can be re-added'.format(remote, cwd)
        )
        command = ['git', 'remote', 'rm', name]
        _git_run(command, cwd=cwd, runas=user, ignore_retcode=ignore_retcode)
    # Add remote
    url = _add_http_basic_auth(url, https_user, https_pass)
    if not isinstance(remote, six.string_types):
        remote = str(remote)
    if not isinstance(url, six.string_types):
        url = str(url)
    command = ['git', 'remote', 'add', remote, url]
    _git_run(command, cwd=cwd, runas=user, ignore_retcode=ignore_retcode)
    if push_url:
        if not isinstance(push_url, six.string_types):
            push_url = str(push_url)
        push_url = _add_http_basic_auth(
            push_url,
            push_https_user,
            push_https_pass
        )
        command = ['git', 'remote', 'set-url', '--push', remote, push_url]
        _git_run(command, cwd=cwd, runas=user, ignore_retcode=ignore_retcode)
    return remote_get(cwd=cwd,
                      remote=remote,
                      runas=user,
                      ignore_retcode=ignore_retcode)


def list_branches(cwd, remote=False, user=None, ignore_retcode=False):
    '''
    .. versionadded:: 2015.8.0

    Return a list of branches

    cwd
        The path to the git checkout

    remote : False
        If ``True``, list remote branches. Otherwise, local branches will be
        listed.

        .. warning::

            This option will only return remote branches of which the local
            checkout is aware, use :py:func:`git.fetch
            <salt.modules.git.fetch>` to update remotes.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Examples:

    .. code-block:: bash

        salt myminion git.list_branches /path/to/repo
        salt myminion git.list_branches /path/to/repo remote=True
    '''
    _check_abs(cwd)
    command = ['git', 'for-each-ref', '--format', '%(refname:short)',
               'refs/{0}/'.format('heads' if not remote else 'remotes')]
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout'].splitlines()


def list_tags(cwd, user=None, ignore_retcode=False):
    '''
    .. versionadded:: 2015.8.0

    Return a list of tags

    cwd
        The path to the git checkout

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Examples:

    .. code-block:: bash

        salt myminion git.list_tags /path/to/repo
    '''
    _check_abs(cwd)
    command = ['git', 'for-each-ref', '--format', '%(refname:short)',
               'refs/tags/']
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout'].splitlines()


def branch(cwd, name, opts='', user=None, ignore_retcode=False):
    '''
    Interface to `git-branch(1)`_

    cwd
        The path to the git checkout

    name
        Name of the branch on which to operate

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            To create a branch based on something other than HEAD, pass the
            name of the revision as ``opts``. If the revision is in the format
            ``remotename/branch``, then this will also set the remote tracking
            branch.

            Additionally, on the Salt CLI, if the opts are preceded with a
            dash, it is necessary to precede them with ``opts=`` (as in the CLI
            examples below) to avoid causing errors with Salt's own argument
            parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-branch(1)`: http://git-scm.com/docs/git-branch


    CLI Examples:

    .. code-block:: bash

        # Set remote tracking branch
        salt myminion git.branch /path/to/repo mybranch opts='--set-upstream-to origin/mybranch'
        # Create new branch
        salt myminion git.branch /path/to/repo mybranch upstream/somebranch
        # Delete branch
        salt myminion git.branch /path/to/repo mybranch opts='-d'
        # Rename branch (2015.8.0 and later)
        salt myminion git.branch /path/to/repo newbranch opts='-m oldbranch'
    '''
    _check_abs(cwd)
    command = ['git', 'branch']
    command.extend(_format_opts(opts))
    command.append(name)
    _git_run(command, cwd=cwd, runas=user, ignore_retcode=ignore_retcode)
    return True


def reset(cwd, opts='', user=None, ignore_retcode=False):
    '''
    Interface to `git-reset(1)`_, returns the stdout from the git command

    cwd
        The path to the git checkout

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` (as in the CLI examples
            below) to avoid causing errors with Salt's own argument parsing.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-reset(1)`: http://git-scm.com/docs/git-reset


    CLI Examples:

    .. code-block:: bash

        # Soft reset to a specific commit ID
        salt myminion git.reset /path/to/repo ac3ee5c
        # Hard reset
        salt myminion git.reset /path/to/repo opts='--hard origin/master'
    '''
    _check_abs(cwd)
    command = ['git', 'reset']
    command.extend(_format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def stash(cwd, opts='', user=None, ignore_retcode=False):
    '''
    Interface to `git-stash(1)`_, returns the stdout from the git command

    cwd
        The path to the git checkout

    opts
        Any additional options to add to the command line, in a single string.
        Use this to complete the ``git stash`` command by adding the remaining
        arguments (i.e.  ``'save <stash comment>'``, ``'apply stash@{2}'``,
        ``'show'``, etc.).  Omitting this argument will simply run ``git
        stash``.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-stash(1)`: http://git-scm.com/docs/git-stash


    CLI Examples:

    .. code-block:: bash

        salt myminion git.stash /path/to/repo 'save work in progress'
        salt myminion git.stash /path/to/repo apply
        salt myminion git.stash /path/to/repo list
    '''
    _check_abs(cwd)
    command = ['git', 'stash']
    command.extend(_format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def config_set(cwd,
               key,
               value,
               user=None,
               ignore_retcode=False,
               is_global=False):
    '''
    Set a key in the git configuration file (.git/config) of the repository or
    globally.

    cwd
        The path to the git checkout. Must be an absolute path, or the word
        ``global``.

        .. versionchanged:: 2015.8.0
            Can now be set to ``global`` instead of an absolute path, to set a
            global git configuration parameter, deprecating the ``is_global``
            parameter.

        .. versionchanged:: 2014.7.0
            Made ``cwd`` argument optional if ``is_global=True``

    key
        The name of the configuration key to set

        .. versionchanged:: 2015.8.0
            Argument renamed from ``setting_name`` to ``key``

    value
        The (new) value to set. Required.

        .. versionchanged:: 2015.8.0
            Argument renamed from ``setting_value`` to ``value``

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    is_global : False
        Set to True to use the '--global' flag with 'git config'

        .. deprecated:: 2015.8.0
            Pass ``global`` as the value of ``cwd`` instead

    CLI Example:

    .. code-block:: bash

        salt myminion git.config_set /path/to/repo user.email me@example.com
        salt myminion git.config_set global user.email foo@bar.com
    '''
    _check_abs(cwd)
    if is_global:
        salt.utils.warn_until(
            'Nitrogen',
            'The \'is_global\' argument to git.config_set has been '
            'deprecated, please set the \'cwd\' argument to \'global\' '
            'instead.'
        )
        cwd = 'global'

    command = ['git', 'config']
    if cwd == 'global':
        command.append('--global')
    elif not os.path.isabs(cwd):
        raise SaltInvocationError(
            'Path must be either \'global\' or an absolute path to a git '
            'checkout'
        )
    command.extend([key, value])
    return _git_run(command,
                    cwd=cwd if cwd != 'global' else None,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def config_get(cwd, key, user=None, ignore_retcode=False):
    '''
    Get the value of a key using ``git config --get``

    cwd
        The path to the git checkout. Must be an absolute path, or the word
        ``global``.

        .. versionchanged:: 2015.8.0
            Can now be set to ``global`` instead of an absolute path, to get
            the value from the global git configuration.

    key
        The name of the configuration key to get

        .. versionchanged:: 2015.8.0
            Argument renamed from ``setting_name`` to ``key``

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0


    CLI Examples:

    .. code-block:: bash

        salt myminion git.config_get /path/to/repo user.name
        salt myminion git.config_get global user.email
    '''
    _check_abs(cwd)
    command = ['git', 'config', '--get']
    if cwd == 'global':
        command.append('--global')
    elif not os.path.isabs(cwd):
        raise SaltInvocationError(
            'The cwd must be either \'global\' or an absolute path to a git '
            'checkout'
        )
    command.append(key)
    return _git_run(command,
                    cwd=cwd if cwd != 'global' else None,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def ls_remote(cwd=None,
              remote='origin',
              ref='master',
              opts='',
              user=None,
              identity=None,
              https_user=None,
              https_pass=None,
              ignore_retcode=False):
    '''
    Interface to `git-ls-remote(1)`_. Returns the upstream hash for a remote
    reference.

    cwd
        The path to the git checkout. Optional (and ignored if present) when
        ``remote`` is set to a URL instead of a remote name.

    remote : origin
        The name of the remote to query. Can be the name of a git remote
        (which exists in the git checkout defined by the ``cwd`` parameter),
        or the URL of a remote repository.

        .. versionchanged:: 2015.8.0
            Argument renamed from ``repository`` to ``remote``

    ref : master
        The name of the ref to query. Can be a branch or tag name, or the full
        name of the reference (for example, to get the hash for a Github pull
        request number 1234, ``ref`` can be set to ``refs/pull/1234/head``

        .. versionchanged:: 2015.8.0
            Argument renamed from ``branch`` to ``ref``

    opts
        Any additional options to add to the command line, in a single string

        .. versionadded:: 2015.8.0

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    identity
        Path to a private key to use for ssh URLs

        .. warning::

            Key must be passphraseless to allow for non-interactive login. For
            greater security with passphraseless private keys, see the
            `sshd(8)`_ manpage for information on securing the keypair from the
            remote side in the ``authorized_keys`` file.

            .. _`sshd(8)`: http://www.man7.org/linux/man-pages/man8/sshd.8.html#AUTHORIZED_KEYS_FILE%20FORMAT

    https_user
        Set HTTP Basic Auth username. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.5.0

    https_pass
        Set HTTP Basic Auth password. Only accepted for HTTPS URLs.

        .. versionadded:: 2015.5.0

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-ls-remote(1)`: http://git-scm.com/docs/git-ls-remote


    CLI Example:

    .. code-block:: bash

        salt myminion git.ls_remote /path/to/repo origin master
        salt myminion git.ls_remote remote=https://mydomain.tld/repo.git ref=mytag opts='--tags'
    '''
    _check_abs(cwd)
    remote = _add_http_basic_auth(remote, https_user, https_pass)
    command = ['git', 'ls-remote']
    command.extend(_format_opts(opts))
    if not isinstance(remote, six.string_types):
        remote = str(remote)
    if not isinstance(ref, six.string_types):
        ref = str(ref)
    command.extend([remote, ref])
    output = _git_run(command,
                      cwd=cwd,
                      runas=user,
                      identity=identity,
                      ignore_retcode=ignore_retcode)['stdout']
    ret = []
    for line in output.splitlines():
        try:
            ret.append(output.split()[0])
        except IndexError:
            continue
    return '\n'.join(ret)


def version(versioninfo=False, user=None):
    '''
    Returns the version of Git installed on the minion

    versioninfo : False
        If ``True``, return the version in a versioninfo list (e.g. ``[2, 5,
        0]``)

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.


    CLI Example:

    .. code-block:: bash

        salt myminion git.version
    '''
    contextkey = 'git.version'
    contextkey_info = 'git.versioninfo'
    if contextkey not in __context__:
        try:
            version_ = _git_run(['git', '--version'], runas=user)['stdout']
        except CommandExecutionError as exc:
            log.error(
                'Failed to obtain the git version (error follows):\n{0}'
                .format(exc)
            )
            version_ = 'unknown'
        try:
            __context__[contextkey] = version_.split()[-1]
        except IndexError:
            # Somehow git --version returned no stdout while not raising an
            # error. Should never happen but we should still account for this
            # possible edge case.
            log.error('Running \'git --version\' returned no stdout')
            __context__[contextkey] = 'unknown'
    if not versioninfo:
        return __context__[contextkey]
    if contextkey_info not in __context__:
        # Set ptr to the memory location of __context__[contextkey_info] to
        # prevent repeated dict lookups
        ptr = __context__.setdefault(contextkey_info, [])
        for part in __context__[contextkey].split('.'):
            try:
                ptr.append(int(part))
            except ValueError:
                ptr.append(part)
    return __context__[contextkey_info]


def is_worktree(worktree_path, user=None):
    '''
    .. versionadded:: 2015.8.0

    This function will attempt to determine if ``worktree_path`` is part of a
    worktree by checking its ``.git`` to see if it is a file containing a
    reference to another gitdir.

    worktree_path
        path to the worktree to be removed

    user
        user under which to run the git command. by default, the command is run
        by the user under which the minion is running.


    CLI Example:

    .. code-block:: bash

        salt myminion git.is_worktree /path/to/repo
    '''
    _check_abs(worktree_path)
    try:
        toplevel = _get_toplevel(worktree_path)
    except CommandExecutionError:
        return False
    gitdir = os.path.join(toplevel, '.git')
    try:
        with salt.utils.fopen(gitdir, 'r') as fp_:
            for line in fp_:
                try:
                    label, path = line.split(None, 1)
                except ValueError:
                    return False
                else:
                    # This file should only contain a single line. However, we
                    # loop here to handle the corner case where .git is a large
                    # binary file, so that we do not read the entire file into
                    # memory at once. We'll hit a return statement before this
                    # loop enters a second iteration.
                    if label == 'gitdir:' and os.path.isabs(path):
                        return True
                    else:
                        return False
    except IOError:
        return False
    return False


def worktree_add(cwd,
                 worktree_path,
                 branch=None,
                 ref=None,
                 reset_branch=None,
                 force=None,
                 detach=False,
                 opts='',
                 user=None,
                 ignore_retcode=False):
    '''
    .. versionadded:: 2015.8.0

    Interface to `git-worktree(1)`_, adds a worktree

    cwd
        The path to the git checkout

    worktree_path
        Path to the new worktree. Can be either absolute, or relative to
        ``cwd``.

    branch
        Name of new branch to create. If omitted, will be set to the basename
        of the ``worktree_path``. For example, if the ``worktree_path`` is
        ``/foo/bar/baz``, then ``branch`` will be ``baz``.

    ref
        Name of the ref on which to base the new worktree. If omitted, then
        ``HEAD`` is use, and a new branch will be created, named for the
        basename of the ``worktree_path``. For example, if the
        ``worktree_path`` is ``/foo/bar/baz`` then a new branch ``baz`` will be
        created, and pointed at ``HEAD``.

    reset_branch : False
        If ``False``, then `git-worktree(1)`_ will fail to create the worktree
        if the targeted branch already exists. Set this argument to ``True`` to
        reset the targeted branch to point at ``ref``, and checkout the
        newly-reset branch into the new worktree.

    force : False
        By default, `git-worktree(1)`_ will not permit the same branch to be
        checked out in more than one worktree. Set this argument to ``True`` to
        override this.

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` to avoid causing errors
            with Salt's own argument parsing.

            All CLI options for adding worktrees as of Git 2.5.0 are already
            supported by this function as of Salt 2015.8.0, so using this
            argument is unnecessary unless new CLI arguments are added to
            `git-worktree(1)`_ and are not yet supported in Salt.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-worktree(1)`: http://git-scm.com/docs/git-worktree


    CLI Examples:

    .. code-block:: bash

        salt myminion git.worktree_add /path/to/repo/main ../hotfix ref=origin/master
        salt myminion git.worktree_add /path/to/repo/main ../hotfix branch=hotfix21 ref=v2.1.9.3
    '''
    _check_abs(cwd)
    if branch and detach:
        raise SaltInvocationError(
            'Only one of \'branch\' and \'detach\' is allowed'
        )

    command = ['git', 'worktree', 'add']
    if detach:
        if force:
            log.warning(
                '\'force\' argument to git.worktree_add is ignored when '
                'detach=True'
            )
        command.append('--detach')
    else:
        if not branch:
            branch = os.path.basename(worktree_path)
        command.extend(['-B' if reset_branch else '-b', branch])
        if force:
            command.append('--force')
    command.extend(_format_opts(opts))
    if not isinstance(worktree_path, six.string_types):
        worktree_path = str(worktree_path)
    command.append(worktree_path)
    if ref:
        if not isinstance(ref, six.string_types):
            ref = str(ref)
        command.append(ref)
    # Checkout message goes to stderr
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stderr']


def worktree_prune(cwd,
                   dry_run=False,
                   verbose=True,
                   expire=None,
                   opts='',
                   user=None,
                   ignore_retcode=False):
    '''
    .. versionadded:: 2015.8.0

    Interface to `git-worktree(1)`_, prunes stale worktree administrative data
    from the gitdir

    cwd
        The path to the main git checkout or a linked worktree

    dry_run : False
        If ``True``, then this function will report what would have been
        pruned, but no changes will be made.

    verbose : True
        Report all changes made. Set to ``False`` to suppress this output.

    expire
        Only prune unused worktree data older than a specific period of time.
        The date format for this parameter is described in the documentation
        for the ``gc.pruneWorktreesExpire`` config param in the
        `git-config(1)`_ manpage.

    opts
        Any additional options to add to the command line, in a single string

        .. note::
            On the Salt CLI, if the opts are preceded with a dash, it is
            necessary to precede them with ``opts=`` to avoid causing errors
            with Salt's own argument parsing.

            All CLI options for pruning worktrees as of Git 2.5.0 are already
            supported by this function as of Salt 2015.8.0, so using this
            argument is unnecessary unless new CLI arguments are added to
            `git-worktree(1)`_ and are not yet supported in Salt.

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-worktree(1)`: http://git-scm.com/docs/git-worktree


    CLI Examples:

    .. code-block:: bash

        salt myminion git.worktree_prune /path/to/worktree
        salt myminion git.worktree_prune /path/to/worktree dry_run=True
        salt myminion git.worktree_prune /path/to/worktree expire=1.day.ago
    '''
    _check_abs(cwd)
    command = ['git', 'worktree', 'prune']
    if dry_run:
        command.append('--dry-run')
    if verbose:
        command.append('--verbose')
    if expire:
        if not isinstance(expire, six.string_types):
            expire = str(expire)
        command.extend(['--expire', expire])
    command.extend(_format_opts(opts))
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def worktree_rm(worktree_path, user=None):
    '''
    .. versionadded:: 2015.8.0

    Recursively removes the worktree located at ``worktree_path``, returning
    ``True`` if successful. This function will attempt to determine if
    ``worktree_path`` is actually a worktree by invoking
    :py:func:`git.is_worktree <salt.modules.git.is_worktree>`. If the path does
    not correspond to a worktree, then an error will be raised and no action will
    be taken.

    .. warning::

        There is no undoing this action. Be **VERY** careful before running
        this function.

    worktree_path
        path to the worktree to be removed

    user
        user under which to run the git command. by default, the command is run
        by the user under which the minion is running.


    CLI Examples:

    .. code-block:: bash

        salt myminion git.worktree_rm /path/to/worktree
    '''
    # No need to run _check_abs on the worktree_path since that will be done
    # when is_worktree is invoked.
    if not os.path.exists(worktree_path):
        raise CommandExecutionError(worktree_path + ' does not exist')
    elif not is_worktree(worktree_path):
        raise CommandExecutionError(worktree_path + ' is not a git worktree')
    try:
        salt.utils.rm_rf(worktree_path)
    except Exception as exc:
        raise CommandExecutionError(
            'Unable to remove {0}: {1}'.format(worktree_path, exc)
        )
    return True


def rev_parse(cwd, rev, opts='', user=None, ignore_retcode=False):
    '''
    .. versionadded:: 2015.8.0

    Interface to `git-rev-parse(1)`_

    cwd
        The path to the git checkout

    rev
        Revision to parse. See the `SPECIFYING REVISIONS`_ section of the
        `git-rev-parse(1)`_ manpage for details on how to format this argument.

    opts
        Any additional options to add to the command line, in a single string

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-rev-parse(1)`: http://git-scm.com/docs/git-rev-parse
    .. _`SPECIFYING REVISIONS`: http://git-scm.com/docs/git-rev-parse#_specifying_revisions


    CLI Examples:

    .. code-block:: bash

        # Get the full SHA1 for HEAD
        salt myminion git.rev_parse /path/to/repo HEAD
        # Get the short SHA1 for HEAD
        salt myminion git.rev_parse /path/to/repo HEAD opts='--short'
        # Get the develop branch's upstream tracking branch
        salt myminion git.rev_parse /path/to/repo 'develop@{upstream}' opts='--abbrev-ref'
        # Get the SHA1 for the commit corresponding to tag v1.2.3
        salt myminion git.rev_parse /path/to/repo 'v1.2.3^{commit}'
    '''
    _check_abs(cwd)
    command = ['git', 'rev-parse']
    command.extend(_format_opts(opts))
    command.append(rev)
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']


def symbolic_ref(cwd,
                 ref,
                 value=None,
                 opts='',
                 user=None,
                 ignore_retcode=False):
    '''
    .. versionadded:: 2015.8.0

    Interface to `git-symbolic-ref(1)`_

    cwd
        The path to the git checkout

    ref
        Symbolic ref to read/modify

    value
        If passed, then the symbolic ref will be set to this value and an empty
        string will be returned.

        If not passed, then the ref to which ``ref`` points will be returned,
        unless ``--delete`` is included in ``opts`` (in which case the symbolic
        ref will be deleted).

    opts
        Any additional options to add to the command line, in a single string

    user
        User under which to run the git command. By default, the command is run
        by the user under which the minion is running.

    ignore_retcode : False
        If ``True``, do not log an error to the minion log if the git command
        returns a nonzero exit status.

        .. versionadded:: 2015.8.0

    .. _`git-symbolic-ref(1)`: http://git-scm.com/docs/git-symbolic-ref


    CLI Examples:

    .. code-block:: bash

        # Get ref to which HEAD is pointing
        salt myminion git.symbolic_ref /path/to/repo HEAD
        # Set/overwrite symbolic ref 'FOO' to local branch 'foo'
        salt myminion git.symbolic_ref /path/to/repo FOO refs/heads/foo
        # Delete symbolic ref 'FOO'
        salt myminion git.symbolic_ref /path/to/repo FOO opts='--delete'
    '''
    _check_abs(cwd)
    command = ['git', 'symbolic-ref']
    opts = _format_opts(opts)
    if value is not None and any(x in opts for x in ('-d', '--delete')):
        raise SaltInvocationError(
            'Value cannot be set for symbolic ref if -d/--delete is included '
            'in opts'
        )
    command.extend(opts)
    command.append(ref)
    if value:
        command.extend(value)
    return _git_run(command,
                    cwd=cwd,
                    runas=user,
                    ignore_retcode=ignore_retcode)['stdout']
