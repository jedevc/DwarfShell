#!/usr/bin/env python3
#  ____                      __ ____  _          _ _
# |  _ \__      ____ _ _ __ / _/ ___|| |__   ___| | |
# | | | \ \ /\ / / _` | '__| |_\___ \| '_ \ / _ \ | |
# | |_| |\ V  V / (_| | |  |  _|___) | | | |  __/ | |
# |____/  \_/\_/ \__,_|_|  |_| |____/|_| |_|\___|_|_|
#

import os
import sys

import re
import enum
import glob
import contextlib

import argparse
import readline

def main():
    # read command line arguments
    parser = argparse.ArgumentParser(prog='dwsh')
    parser.add_argument('file', nargs='?', type=open)
    args = parser.parse_args()

    # detect if reading directly from a terminal
    if os.isatty(0):
        args.prompt = '$ '
    else:
        args.prompt = ''

    # start the shell
    sh = Shell(args.prompt, args.file)
    sh.run()

class Shell:
    '''
    The main shell class.

    Args:
        prompt: The input to display before reading each line.
        source: A file-like object for reading input from.
    '''

    def __init__(self, prompt, source=None):
        self.prompt = prompt
        self.source = source

        self.builtins = {
            'exit': self._builtin_exit,
            'pwd': self._builtin_pwd,
            'cd': self._builtin_cd
        }

    def run(self):
        '''
        Run the shell in a loop.
        '''

        while True:
            line = self.readline()
            if line is None: break

            self.execute(line)

    def readline(self):
        '''
        Read a command from the source file, or if it has not been provided,
        then from stdin.

        Returns:
            A raw command string.
        '''

        if self.source:
            raw = self.source.readline()
            return raw if len(raw) > 0 else None
        else:
            while True:
                try:
                    raw = input(self.prompt)
                except EOFError:
                    return None

                if len(raw) > 0:
                    return raw

    def execute(self, raw):
        '''
        Execute a command in the form of a raw string.

        Args:
            raw: The raw string to parse and execute.
        '''

        # parse command
        tokens = Tokenizer(raw)
        parser = Parser(tokens)
        try:
            root = parser.parse()
        except ParseError as e:
            self.error('parse error', str(e))
            return

        # execute command
        if root:
            try:
                root.execute(self.builtins, os.environ, Hooks())
            except CommandNotFoundError as e:
                self.error('command not found', e.command)
            except FileNotFoundError as e:
                self.error('no such file or directory', e.filename)
            except IsADirectoryError as e:
                self.error('is a directory', e.filename)
            except PermissionError as e:
                self.error('permission denied', e.filename)
            finally:
                root.wait()

    def error(self, summary, details):
        '''
        Print an error to the console.

        Args:
            summary: A summary of what happened.
            details: The subject of the error.
        '''

        print(f'dwsh: {summary}: {details}', file=sys.stderr)

    # various shell builtins
    def _builtin_exit(self, name, n=0):
        sys.exit(n)

    def _builtin_pwd(self, name):
        wd = os.getcwd()
        print(wd)

    def _builtin_cd(self, name, d):
        os.chdir(d)

class TokenType(enum.Enum):
    '''
    Token types that can be recognized by the Tokenizer.
    '''

    WORD = enum.auto()
    REDIRECT_OUT = enum.auto()
    REDIRECT_APPEND = enum.auto()
    REDIRECT_IN = enum.auto()
    PIPE = enum.auto()
    COMMAND_END = enum.auto()
    EOF = enum.auto()
    UNKNOWN = enum.auto()

class Token:
    '''
    A string with an assigned meaning used during lexical analysis.

    Args:
        ttype: The token meaning.
        lexeme: The token value.
        position: The location of the token in the stream.
    '''

    def __init__(self, ttype, lexeme=None, position=None):
        self.lexeme = lexeme
        self.ttype = ttype
        self.position = position

class Tokenizer:
    '''
    Performs lexical analysis on a raw string.

    Args:
        string: The raw string on which to operate.
    '''

    def __init__(self, string):
        self.string = string
        self.position = -1
        self.char = None

        self.read()

    # regular expression for matching word characters
    WORD_CHARS = re.compile('[^><|;]')

    def token(self):
        '''
        Read a single token from the stream.

        Returns:
            The generated token.

        Throws:
            May throw a ValueError in the case that the input is malformed and
            a token cannot be correctly generated from it.
        '''

        # ignore whitespace
        while self.char and self.char.isspace():
            self.read()

        if self.char == None:
            # end-of-file
            return Token(TokenType.EOF, None, self.position)
        elif self.char == '>':
            # output redirection
            start = self.position
            if self.read() == '>':
                self.read()
                return Token(TokenType.REDIRECT_APPEND, None, start)
            else:
                return Token(TokenType.REDIRECT_OUT, None, start)
        elif self.char == '<':
            # input redirection
            token = Token(TokenType.REDIRECT_IN, None, self.position)
            self.read()
            return token
        elif self.char == '|':
            # pipe
            token = Token(TokenType.PIPE, None, self.position)
            self.read()
            return token
        elif self.char == ';':
            # command seperator
            token = Token(TokenType.COMMAND_END, None, self.position)
            self.read()
            return token
        elif self.char in '\'"':
            # quoted word
            end = self.char
            self.read()

            start = self.position
            value = []
            while self.char and self.char != end:
                value.append(self.char)
                self.read()
            if self.char is None:
                raise ValueError('unexpected end of line while reading quoted word')
            else:
                self.read()

            return Token(TokenType.WORD, ''.join(value), start)
        elif Tokenizer.WORD_CHARS.match(self.char):
            # single word
            start = self.position
            value = []
            while self.char and Tokenizer.WORD_CHARS.match(self.char) and not self.char.isspace():
                value.append(self.char)
                self.read()

            return Token(TokenType.WORD, ''.join(value), start)
        else:
            # unknown
            token = Token(TokenType.UNKNOWN, self.char, self.position)
            self.read()
            return token

    def __iter__(self):
        '''
        Utility iterator to allow easy creation of a stream of tokens.
        '''

        while True:
            token = self.token()
            yield token

            if token.ttype == TokenType.EOF: break

    def read(self):
        '''
        Read a single char from the stream and store it in self.char.

        Returns:
            The value of self.char.
        '''

        self.position += 1
        if self.position < len(self.string):
            self.char = self.string[self.position]
        else:
            self.char = None
        return self.char

class Parser:
    '''
    Parses a stream of tokens into an Abstract Syntax Tree for later execution.

    Args:
        tokens: The stream of tokens.
    '''

    def __init__(self, tokens):
        self.tokens = iter(tokens)
        self.token = None
        self.last = None

        self.next()

    def parse(self):
        '''
        Parse the stream of tokens.

        Returns:
            The root node of the Abstract Syntax Tree.

        Throws:
            May throw a ParseError in the case that the stream of tokens is
            malformed.
        '''

        root = self.lines()
        self.expect(TokenType.EOF)

        return root

    def lines(self):
        base = self.line()
        if self.accept(TokenType.COMMAND_END):
            other = self.lines()
            if base and other:
                return MultiNode(base, other)
            elif base:
                return base
            elif other:
                return other
            else:
                return None
        else:
            return base

    def line(self):
        base = self.command()
        if base:
            redirs = self.redirections()
            if redirs:
                base = RedirectionsNode(base, redirs)

            if self.accept(TokenType.PIPE):
                other = self.line()
                if other is None:
                    raise ParseError('expected command')
                return PipeNode(base, other)

        return base

    def command(self):
        if self.accept(TokenType.WORD):
            args = [self.last.lexeme]
            while self.accept(TokenType.WORD):
                args.append(self.last.lexeme)

            return CommandNode(args)

    def redirections(self):
        redirs = []
        redir = self.redirection()
        while redir:
            redirs.append(redir)
            redir = self.redirection()

        if len(redirs) > 0:
            return Redirections(redirs)

    def redirection(self):
        # TODO: recognize other types of redirections
        if self.accept(TokenType.REDIRECT_OUT):
            filename = self.expect(TokenType.WORD).lexeme
            return Redirection(1, (filename, os.O_CREAT | os.O_WRONLY | os.O_TRUNC))
        elif self.accept(TokenType.REDIRECT_APPEND):
            filename = self.expect(TokenType.WORD).lexeme
            return Redirection(1, (filename, os.O_CREAT | os.O_WRONLY | os.O_APPEND))
        elif self.accept(TokenType.REDIRECT_IN):
            filename = self.expect(TokenType.WORD).lexeme
            return Redirection(0, (filename, os.O_RDONLY))

    def next(self):
        self.last = self.token
        self.token = next(self.tokens, None)
        return self.token

    def accept(self, ttype):
        if self.token and self.token.ttype == ttype:
            self.next()
            return self.last

    def expect(self, ttype):
        result = self.accept(ttype)
        if result:
            return result
        else:
            raise ParseError(f'expected token {ttype}')

class Node:
    '''
    A single node in the Abstract Syntax Tree.
    '''

    def execute(self, builtins, variables, hooks):
        '''
        Execute the node.

        Args:
            builtins: A dict of builtin commands.
            variables: A dict of variables.
            hooks: A collection of hooks that can be called during execution.
        '''

        pass

    def wait(self):
        '''
        Wait for the execution of the node to finish.
        '''

        pass

class CommandNode(Node):
    '''
    A node that contains a single shell command.

    Args:
        args: The arguments to be passed to the executable. The first argument
            should be the name of the executable.
    '''

    def __init__(self, args):
        self.args = args

        self.pid = None

    def execute(self, builtins, variables, hooks):
        # variable expansion
        args = [self.expandvars(arg, variables) for arg in self.args]

        # globbing
        args = [self.glob(arg) for arg in self.args]
        args = [item for sublist in args for item in sublist]

        command = args[0]

        if command in builtins:
            hooks.execute(command, args)
            builtins[command](*args)
        else:
            command = self.lookup(command, variables['PATH'].split(':'))

            # fork process
            pid = os.fork()
            if pid == 0:
                # child process
                hooks.execute(command, args)
                hooks.fork()
                os.execv(command, args)
            else:
                # parent process
                self.pid = pid

    def wait(self):
        if self.pid:
            os.waitpid(self.pid, 0)

    def lookup(self, filename, path):
        '''
        Find the filename in the provided path.

        Args:
            filename: The filename to search for.
            path: A list of places to search.

        Returns:
            The full path if found, None if not.
        '''

        if filename.startswith(('/', './'))  and os.path.exists(filename):
            return filename

        for di in path:
            possible = os.path.join(di, filename)
            if os.path.exists(possible):
                return possible

        raise CommandNotFoundError(filename)

    def expandvars(self, raw, variables):
        '''
        Expand variables.

        Args:
            raw: The raw string to expand.
            variables: A dictionary containing variables to replace.

        Returns:
            The expanded string.
        '''

        result = []

        i = 0
        while i < len(raw):
            if raw[i] == '$':
                # variable expansion
                name = []

                i += 1
                if raw[i] == '{':
                    i += 1
                    while True:
                        if i >= len(raw):
                            raise ValueError('expected end brace')
                        elif raw[i] == '}':
                            i += 1
                            break
                        else:
                            name.append(raw[i])
                            i += 1
                else:
                    while i < len(raw) and (raw[i].isalpha() or raw[i] == '_'):
                        name.append(raw[i])
                        i += 1

                name = ''.join(name)
                value = str(variables[name])

                result.append(value)
            else:
                # standard character
                result.append(raw[i])
                i += 1

        return ''.join(result)

    def glob(self, raw):
        '''
        Calculate the globbed filenames.

        Args:
            raw: The raw string to expand.

        Returns:
            The expanded string.
        '''

        if '*' in raw:
            return glob.glob(raw, recursive=True)
        else:
            return [raw]

class MultiNode(Node):
    '''
    A node that executes two nodes sequentially.

    Args:
        first: The first node to execute.
        second: The second node to execute.
    '''

    def __init__(self, first, second):
        self.first = first
        self.second = second

    def execute(self, builtins, variables, hooks):
        self.first.execute(builtins, variables, hooks)
        self.first.wait()

        self.second.execute(builtins, variables, hooks)
        self.second.wait()

class PipeNode(Node):
    '''
    A node that executes two nodes in parallel, forwarding the output of the
    first to the input of the second.

    Args:
        first: The node to pipe the output from.
        second: The node to pipe the input into.
    '''

    def __init__(self, first, second):
        self.first = first
        self.second = second

    def execute(self, builtins, variables, hooks):
        # setup pipe
        read, write = os.pipe()
        inp = Redirection(0, read)
        outp = Redirection(1, write)

        with outp:
            self.first.execute(builtins, variables, Hooks(hooks, fork=lambda: inp.close()))

        outp.close()

        with inp:
            self.second.execute(builtins, variables, hooks)

    def wait(self):
        self.first.wait()
        self.second.wait()

class RedirectionsNode(Node):
    '''
    A node that performs a number of IO redirections.

    Args:
        base: The base node to operate on.
        redirections: The redirections to apply.
    '''

    def __init__(self, base, redirections):
        self.base = base
        self.redirections = redirections

    def execute(self, builtins, variables, hooks):
        with self.redirections:
            self.base.execute(builtins, variables, hooks)

    def wait(self):
        self.base.wait()

class Hooks:
    '''
    Tracker of various hooks to be run during execution.

    Args:
        base: A hook to copy existing hooks from.
        execute: Hooks to be run upon command execution.
        fork: Hooks to be run upon a process fork.
    '''

    def __init__(self, base=None, execute=None, fork=None):
        if base:
            self._execute = base._execute + Hooks._listify(execute)
            self._fork = base._fork + Hooks._listify(fork)
        else:
            self._execute = Hooks._listify(execute)
            self._fork = Hooks._listify(fork)

    def execute(self, command, args):
        for hook in self._execute: hook(command, args)

    def fork(self):
        for hook in self._fork: hook()

    def _listify(value):
        if value is None:
            return []
        try:
            return list(value)
        except TypeError:
            return [value]

class Redirection:
    '''
    Helps perform a single file redirection.

    Args:
        fd: The file descriptor to modify.
        newfd: The new file descriptor.
    '''

    def __init__(self, fd, params):
        self.fd = fd
        self.backup = os.dup(fd)

        self.newfd = None
        try:
            if len(params) == 2:
                self.filename, self.mode = params
                self.permissions = 0o644
            elif len(params) == 3:
                self.filename, self.mode, self.permissions = params
            else:
                raise ValueError('invalid file open parameters')
        except TypeError:
            self.newfd = params

    def open(self):
        self.newfd = os.open(self.filename, self.mode, self.permissions)

    def close(self):
        os.close(self.newfd)

    def __enter__(self):
        if self.newfd is None:
            self.open()
        os.dup2(self.newfd, self.fd)

    def __exit__(self, type, value, traceback):
        os.dup2(self.backup, self.fd)

class Redirections:
    '''
    Helps perform multiple file redirections.

    Args:
        redirections: A list of redirections.
    '''

    def __init__(self, redirections):
        self.redirections = redirections

        self.stack = None

    def __enter__(self):
        if len(self.redirections) > 0:
            self.stack = contextlib.ExitStack()
            for redirection in self.redirections:
                self.stack.enter_context(redirection)

    def __exit__(self, type, value, traceback):
        if self.stack:
            self.stack.close()
            self.stack = None

class ParseError(ValueError):
    pass

class CommandNotFoundError(Exception):
    def __init__(self, command):
        self.command = command

if __name__ == "__main__":
    main()
