import os
import sys

import re

import enum
from enum import Enum

def main():
    sh = Shell()
    sh.run()

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
        Run the shell.
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

        return input('$ ')

    def execute(self, raw):
        '''
        Execute a command in the form of a raw string.
        '''

        tokens = Tokenizer(raw)

        parser = Parser(tokens)
        root = parser.parse()
        root.execute(self.builtins)
        root.wait()

    # various shell builtins
    def _builtin_exit(self, name, n=0):
        sys.exit(n)

    def _builtin_pwd(self, name):
        wd = os.getcwd()
        print(wd)

    def _builtin_cd(self, name, d):
        os.chdir(d)

class TokenType(Enum):
    '''
    Token types that are recognized by the Tokenizer.
    '''

    WORD = enum.auto()
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

        return self.command()

    def command(self):
        if self.accept(TokenType.WORD):
            command = self.last.lexeme

            args = []
            while self.accept(TokenType.WORD):
                args.append(self.last.lexeme)

            self.expect(TokenType.EOF)

            return CommandNode(command, args)
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

class Node:
    '''
    A single node in the Abstract Syntax Tree.
    '''

    def execute(self, builtins):
        '''
        Execute the node.

        Args:
            builtins: A dict of builtin commands.
        '''

        pass

    def wait(self):
        '''
        Wait for the execution of the node to complete.
        '''

        pass

class CommandNode:
    '''
    A node that contains a single shell command.
    '''

    def __init__(self, command, args):
        self.command = command

        self.args = args
        self.args.insert(0, command)

        self.pid = None

    def execute(self, builtins):
        if self.command in builtins:
            builtins[self.command](*self.args)
        else:
            pid = os.fork()
            if pid == 0:
                # child process
                os.execv(self.full_command, self.args)
            else:
                # parent process
                self.pid = pid

    def wait(self):
        if self.pid is not None:
            os.waitpid(self.pid, 0)

    @property
    def full_command(self):
        if os.path.exists(self.command):
            return self.command

        path = os.environ['PATH'].split(':')
        for di in path:
            cmd = os.path.join(di, self.command)
            if os.path.exists(cmd):
                return cmd

        raise FileNotFoundError('command not found')

if __name__ == "__main__":
    main()
