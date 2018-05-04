#!/usr/bin/env python3

import os
import sys

import readline

import contextlib

import enum
from enum import Enum

def main():
    sh = Shell()
    sh.run()

# shell
class Shell:
    '''
    The main shell class.
    '''

    def __init__(self):
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
            try:
                line = self.readline()
                self.execute(line)
            except EOFError:
                sys.exit(0)

    def readline(self):
        '''
        Read a command from stdin to execute.

        Returns:
            A raw string read from stdin.
        '''

        while True:
            raw = input('$ ')
            if len(raw) > 0:
                return raw

    def execute(self, raw):
        '''
        Execute a command in the form of a raw string.
        '''

        tokens = Tokenizer(raw)

        parser = Parser(tokens)
        root = parser.parse()
        if root:
            try:
                root.execute(self.builtins, Hooks())
            except CommandNotFoundError as e:
                print(f'dwsh: command not found: {e.command}')
            except FileNotFoundError as e:
                print(f'dwsh: no such file or directory: {e.filename}')
            except IsADirectoryError as e:
                print(f'dwsh: is a directory: {e.filename}')
            except PermissionError as e:
                print(f'dwsh: permission denied: {e.filename}')
            finally:
                root.wait()

    # various shell builtins
    def _builtin_exit(self, name, n=0):
        sys.exit(n)

    def _builtin_pwd(self, name):
        wd = os.getcwd()
        print(wd)

    def _builtin_cd(self, name, d):
        os.chdir(d)

# lexical analysis
class TokenType(Enum):
    '''
    Token types that are recognized by the Tokenizer.
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
    A string with an assigned meaning.

    Args:
        ttype: The token meaning.
        lexeme: The token value (optional).
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
            start = self.position
            if self.read() == '>':
                self.read()
                return Token(TokenType.REDIRECT_APPEND, None, start)
            else:
                return Token(TokenType.REDIRECT_OUT, None, start)
        elif self.char == '<':
            token = Token(TokenType.REDIRECT_IN, None, self.position)
            self.read()
            return token
        elif self.char == '|':
            token = Token(TokenType.PIPE, None, self.position)
            self.read()
            return token
        elif self.char == ';':
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
        elif self.char.isprintable():
            # single word
            start = self.position
            value = []
            while self.char and self.char.isprintable() and not self.char.isspace():
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

# syntax analysis
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
            May throw a ValueError in the case that the stream of tokens is
            malformed.
        '''

        root = self.commands()
        self.expect(TokenType.EOF)

        return root

    def commands(self):
        base = self.command()
        if self.accept(TokenType.COMMAND_END):
            other = self.commands()
            if base and other:
                return MultiNode(base, other)
            else:
                return other
        else:
            return base

    def command(self):
        if self.accept(TokenType.WORD):
            command = self.last.lexeme

            args = []
            while self.accept(TokenType.WORD):
                args.append(self.last.lexeme)

            node = CommandNode(command, args)

            redirs = self.redirections()
            if redirs:
                node = RedirectionsNode(node, redirs)

            if self.accept(TokenType.PIPE):
                return PipeNode(node, self.command())
            else:
                return node
        else:
            return None

    def redirections(self):
        redirs = []
        redir = self.redirection()
        while redir:
            redirs.append(redir)
            redir = self.redirection()

        if len(redirs) > 0:
            return Redirections(redirs)
        else:
            return None

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
        else:
            return None

    def next(self):
        self.last = self.token
        self.token = next(self.tokens, None)
        return self.token

    def accept(self, ttype):
        if self.token and self.token.ttype == ttype:
            self.next()
            return self.last
        else:
            return None

    def expect(self, ttype):
        result = self.accept(ttype)
        if result:
            return result
        else:
            raise ValueError(f'expected token to be {ttype}, instead got {self.token.ttype}')

# abstract syntax tree
class Node:
    '''
    A single node in the Abstract Syntax Tree.
    '''

    def execute(self, builtins, hooks):
        '''
        Execute the node.

        Args:
            builtins: A dict of builtin commands.
            hooks: A collection of hooks that can be called during execution.
        '''

        pass

    def wait(self):
        '''
        Wait for the execution of the node to finish.
        '''

        pass

class CommandNotFoundError(Exception):
    def __init__(self, command):
        self.command = command

class CommandNode(Node):
    '''
    A node that contains a single shell command.

    Args:
        command: The name of the executable to run (will be looked up in PATH).
        args: The arguments to be passed to the executable.
    '''

    def __init__(self, command, args):
        self.command = command

        self.args = args
        self.args.insert(0, command)

        self.pid = None

    def execute(self, builtins, hooks):
        if self.command in builtins:
            hooks.execute(self.command, self.args)
            builtins[self.command](*self.args)
        else:
            cmd = self.full_command()

            pid = os.fork()
            if pid == 0:
                # child process
                hooks.execute(cmd, self.args)
                hooks.fork()
                os.execv(cmd, self.args)
            else:
                # parent process
                self.pid = pid

    def wait(self):
        if self.pid:
            os.waitpid(self.pid, 0)

    def full_command(self):
        if os.path.exists(self.command):
            return self.command

        path = os.environ['PATH'].split(':')
        for di in path:
            cmd = os.path.join(di, self.command)
            if os.path.exists(cmd):
                return cmd

        raise CommandNotFoundError(self.command)

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

    def execute(self, builtins, hooks):
        self.first.execute(builtins, hooks)
        self.first.wait()

        self.second.execute(builtins, hooks)
        self.second.wait()

class PipeNode(Node):
    '''
    A node that forwards the output of one node to the input of another.

    Args:
        first: The node to pipe the output from.
        second: The node to pipe the input into.
    '''

    def __init__(self, first, second):
        self.first = first
        self.second = second

    def execute(self, builtins, hooks):
        read, write = os.pipe()
        inp = Redirection(0, read)
        outp = Redirection(1, write)

        with outp:
            self.first.execute(builtins, Hooks(hooks, fork=lambda: inp.close()))

        outp.close()

        with inp:
            self.second.execute(builtins, hooks)

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

    def execute(self, builtins, hooks):
        with self.redirections:
            self.base.execute(builtins, hooks)

    def wait(self):
        self.base.wait()

# helpers
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

if __name__ == "__main__":
    main()
