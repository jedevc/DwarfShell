# DwarfShell

DwarfShell is a simple one-file, no-dependency shell that runs on any linux
system with python.

This was mainly built as a pet project to try and understand the linux
ecosystem a little better and to take the mystery out of commonly used tools.
Hopefully, the program is well commented enough to be able to easily pull apart
and understand how it works.

It is *not* meant to be feature complete, so it probably is not a good
replacement for an everyday shell. However, it does support several more
complex features, such as input/ouput redirection, piping and a few types of
expansions.

## Downloading

As DwarfShell is just one file, downloading it is very easy.  You can do so in
two ways, using a file downloader such as wget, or using git clone. Either of
these are good, however, using git will allow you to more easily access
upstream changes.

Using wget:

	wget https://raw.githubusercontent.com/jedevc/DwarfShell/master/dwsh.py

Using git clone:

	git clone https://github.com/jedevc/DwarfShell.git
	cd DwarfShell

## Running

Running DwarfShell is just as easy as downloading it, just execute `dwsh.py`.

	./dwsh.py

You can also manually invoke the python interpreter if you want.

	python dwsh.py

If you experience any issues, please report them
[here](https://github.com/jedevc/DwarfShell/issues/new).

## Installation

If for some reason you actually want to install DwarfShell, then just copy
`dwsh.py` to a directory in your path.

## License

DwarfShell uses the Unlicense and so is completely free and released into the
public domain. Do whatever you feel like doing with it, although some
attribution might be nice :)
