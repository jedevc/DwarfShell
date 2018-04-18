import os
import sys

import re

import enum
from enum import Enum

def main():
    sh = Shell()
    sh.run()

class Shell:
    def __init__(self):
        self.builtins = {
            'exit': self._builtin_exit,
            'pwd': self._builtin_pwd,
            'cd': self._builtin_cd
        }

    def run(self):
        while True:
            try:
                line = self.readline()
                self.execute(line)
            except EOFError:
                sys.exit(0)

    def readline(self):
        return input('$ ')

    def execute(self, line):
        tokens = Tokenizer(line)

        parser = Parser(tokens)
        root = parser.parse()
        root.execute(self.builtins)
        root.wait()

    def _builtin_exit(self, name, n=0):
        sys.exit(n)

    def _builtin_pwd(self, name):
        wd = os.getcwd()
        print(wd)

    def _builtin_cd(self, name, d):
        os.chdir(d)

class TokenType(Enum):
    WORD = enum.auto()
    EOF = enum.auto()
    UNKNOWN = enum.auto()

class Token:
    def __init__(self, ttype, lexeme=None, position=None):
        self.lexeme = lexeme
        self.ttype = ttype
        self.position = position

class Tokenizer:
    def __init__(self, string):
        self.string = string
        self.position = -1
        self.char = None

        self.read()

    def read(self):
        self.position += 1
        if self.position < len(self.string):
            self.char = self.string[self.position]
        else:
            self.char = None
        return self.char

    def token(self):
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
                raise ValueError('unexpected end of line')
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
        while True:
            token = self.token()
            yield token

            if token.ttype == TokenType.EOF: break

class Parser:
    def __init__(self, tokens):
        self.tokens = iter(tokens)
        self.token = None
        self.last = None

        self.next()

    def parse(self):
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
            print(self.token.lexeme)
            raise ValueError(f'expected token to be {ttype}, instead got {self.token.ttype}')

class Node:
    def execute(self, builtins):
        pass

    def wait(self):
        pass

class CommandNode:
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
