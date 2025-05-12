#!/usr/bin/env python3

from rich.console import Console
from rich.text import Text
import diff_match_patch as dmp_module


def show_diffblock(str1, str2, quoteid, filename1, filename2, line1, line2):
    """Shows a single diff for a pair of strings.

    Args:
        str1,str2 (str): strings to compare,
        quoteid (str): quote ID to show in the heading,
        filenameN (str): filename for the quote in strN
        lineN (int): line number for `strN` in the file `filenameN`.

    Returns:
        different (bool): True iff there were strings found
    """
    dmp = dmp_module.diff_match_patch()
    diffs = dmp.diff_main(str1, str2)
    #dmp.diff_cleanupSemantic(diffs)  # Clean up for readability

    result = Text()
    different = False

    result.append(Text(f"=== [begin of "))
    result.append(Text(f"{quoteid}", style="cyan"))
    result.append("] " + "".join(["=" for _ in range(max(0, 70 - len(f"{quoteid}")-16))]) + "\n")
    result.append(Text(f"Locations: {filename1}:{line1} (vs {filename2}:{line2})\n\n"))

    for op, data in diffs:
        if op == 0:  # Equal
            result.append(data)
        elif op == 1:  # Insert
            result.append(Text(data, style="green underline"))
            different = True
        elif op == -1:  # Delete
            result.append(Text(data, style="red strike"))
            different = True

    result.append("\n\n=== [end of ")
    result.append(Text(f"{quoteid}", style="cyan"))
    result.append("] " + "".join(["=" for _ in range(max(0, 70 - len(f"{quoteid}")-14))]))

    return different, result


class Quote():
    def __init__(self, text="", filename=None,
                 locstart=None, locend=None):
        self.text = text
        self.filename = filename
        self.locstart = locstart
        self.locend = locend

# preprocessors and postprocessors

import re
def replace_single_newlines(text):
    """Replaces a single newline not followed by another one."""
    return re.sub(r'(?<!\n)\n(?!\n)', ' ', text)

def squash_whitespaces(text):
    """Removes multiple spaces and newlines."""
    return ' '.join(text.split())

def squash_spaces_tabs(text):
    return ' '.join(re.split('[ \t\f\v]+', text))

class FileScanner:
    def __init__(self, preprocessors = [
            squash_whitespaces],
                 postprocessors = [
                     squash_spaces_tabs,
                     replace_single_newlines,
                 ],
                 ignored_chars=":/|[]{}!",
                 verbose=True):
        self.verbose = verbose
        self.preprocessors = preprocessors
        self.postprocessors = postprocessors
        self.quotes = dict()
        self.canonical = dict()
        self.qstatus = dict()
        self.ignored_chars = ignored_chars
        self.quotes_open = 0
        
    def parse_line(self, instring, filename=None, line=None):
        """Parses a single string."""

        string = instring
        for p in self.preprocessors:
            string = p(string)

        # check if this is an opening clause
        if string.lower().startswith("% begin quote"):
            # trying to add a new quote
            quoteid = string[len("% begin quote"):]
            for s in self.ignored_chars:
               quoteid = quoteid.replace(s, "")

            quoteid = quoteid.strip()

            if quoteid == "":
                print(f"Warning: {filename}:{line} -- ignoring (opening) a quote without id.")
                return # ignore
            quoteid=quoteid.strip().lower()

            if (quoteid in self.quotes) and (self.qstatus[quoteid] == "open"):
                raise ValueError(f"{filename}:{line} -- ERROR: {quoteid} is already open. Duplicate quote id?")
                exit(1)

            self.qstatus[quoteid] = "open"
            if quoteid not in self.quotes:
                self.quotes[quoteid] = []

            self.quotes[quoteid].append(Quote(text="",
                                              filename=filename,
                                              locstart=line, locend=None))

            if '!' in string:
                # This is a canonical version of the quote
                # TODO: warning if already defined
                if self.verbose:
                    print(f"INFO: Marking {filename} as canonical for {quoteid}")
                self.canonical[quoteid] = self.quotes[quoteid][-1]

            self.quotes_open += 1
            return

        # check if this is a closing clause
        if string.lower().startswith("% end quote"):
            # trying to close a quote
            quoteid = string[len("% end quote"):].strip()
            for s in self.ignored_chars:
               quoteid = quoteid.replace(s, "")

            quoteid=quoteid.strip().lower()

            if (self.quotes_open == 1) and (quoteid==""):
                # It is obvious which quote to close
                for candquote in self.quotes:
                    if self.qstatus[candquote] == "open":
                        quoteid = candquote

                if quoteid != "":
                    if self.verbose:
                        print(f"Info: {filename}:{line} -- closing quote '{quoteid}' (no other options).")

            if quoteid == "":
                print(f"Warning: {filename}:{line} -- a closing quote directive without an id. ")
                if self.quotes_open > 1:
                    print("However, this is ambiguous, as currently open quotes are:")
                    for qid in self.quotes:
                        if self.qstatus[qid] == "open":
                            print(f"- {qid}")
                    exit(1)
                else:
                    print(" (No quotes are open.)")
                    return # ignore


            if quoteid not in self.quotes:
                raise ValueError(f"{filename}:{line} -- ERROR: did not see quote id '{quoteid}' before. Wrong quote id?")
                exit(1)

            if self.qstatus[quoteid] != "open":
                raise ValueError(f"{filename}:{line} -- ERROR: {quoteid} is not open (current status: '{self.qstatus[quoteid]}'). Wrong quote id?")
                exit(1)

            self.qstatus[quoteid] = "closed"
            quote = self.quotes[quoteid][-1]
            quote.locend = line
            self.quotes_open -= 1

            for p in self.postprocessors:
                quote.text = p(quote.text)
            return

        # just add the line to the text of all open quotes
        for quoteid in self.quotes:
            if self.qstatus[quoteid] == "open":
                self.quotes[quoteid][-1].text += string + '\n'

    def add_file(self, filename, verbose=None):
        if verbose is None:
            verbose = self.verbose

        if verbose:
            console = Console()

        with open(filename, 'r') as infile:
            lines = infile.readlines()
            if len(lines)==0:
                raise ValueError(f"{filename}: empty file.")

            if verbose:
                console.print(Text("INFO: ", style="cyan"), end="")
                console.print(f"read {len(lines)} lines from {filename}. Parsing...\n")

            for n, line in enumerate(lines):
                self.parse_line(line, filename=filename, line=(n+1))

            if self.verbose:
                print(f"Recovered quotes:")
                for quoteid in self.quotes:
                    print(f"Quote id={quoteid}:")
                    for quote in self.quotes[quoteid]:
                        print(f"In {quote.filename}, lines {quote.locstart}--{quote.locend}:")
                        print(quote.text)
                        print("\n\n")

            if self.quotes_open > 0:
                print("Warning: open quotes remaining at the end of the file:")
                for qid in self.quotes:
                    if self.qstatus[qid] == "open":
                        print(f"- {qid}")

    def compare_quotes(self):
        """Performs the actual comparison of the (scanned) quotes."""
        console = Console()

        for quoteid in self.quotes:
            if len(self.quotes[quoteid]) == 1:
                print(f"Warning: only one case of {quoteid} (from {self.quotes[quoteid][0].filename})")

            else:
                if quoteid not in self.canonical:
                    self.canonical[quoteid] = self.quotes[quoteid][0]
                    if self.verbose:
                        print(f"INFO: {self.canonical[quoteid].filename}:{self.canonical[quoteid].locstart} is set as canonical for {quoteid} (default)")

                cquote = self.canonical[quoteid]
                if self.verbose:
                    print(f"INFO: Canonical for {quoteid} is set from {cquote.filename}:{cquote.locstart}")

                for quote in self.quotes[quoteid]:
                    if (cquote.filename == quote.filename) and \
                    (cquote.locstart == quote.locstart) and \
                    (cquote.locend == quote.locend):
                        continue  # that's the same entry

                    print(f"Comparing '{quoteid}' from {quote.filename} vs {cquote.filename}...", end="")
                    different, res = show_diffblock(quote.text, cquote.text, quoteid,
                                                    quote.filename, cquote.filename,
                                                    quote.locstart, cquote.locstart)

                    if different:
                        console.print()
                        console.print(res, width=70, overflow="fold")
                    else:
                        console.print("(no differences)")

import glob
import argparse

def expand_filenames(patterns):
    """Expands the wildcards/globs in the arguments"""
    files = []
    for pattern in patterns:
        matched = glob.glob(pattern)
        if matched:
            files.extend(matched)
        else:
            files.append(pattern)
    return files

def main():
    parser = argparse.ArgumentParser(prog="anxiety",
                                     description='Input files to worry about.')
    parser.add_argument('files', nargs='+', help='Input file(s) or glob pattern(s)')
    args = parser.parse_args()

    fs = FileScanner(verbose=False)
    for infile in expand_filenames(args.files):
        fs.add_file(infile)

    fs.compare_quotes()

if __name__ == '__main__':
    main()

## Testing and experimentation code
def try_scan():
    fs = FileScanner(verbose=False)
    fs.add_file("tests/outputs.tex")
    fs.add_file("tests/response_letter.tex")
    fs.compare_quotes()

def try_filescanner():
    fs = FileScanner()
    string = "  %   begin quote  |/ this is A new QuoTe "
    print(f"Before:\n{string}|")
    print(f"After:\n{fs.parse_line(string, 'hypothetical', 5)}|")

def try_addfile():
    fs = FileScanner()
    fs.add_file("tests/outputs.tex")

def try_showdiff():
    # Example usage
    str1 = "Hello, wonderful...\n... world!"
    str2 = "Hello, wonderful...\n... modified world!"

    d1, r1 = show_diffblock(str1, str2,"q1","f1","f2",1,2)

    d2, r2 = show_diffblock(str2, str1,"q1", "f2","f1",2,1)

    console = Console()
    print(f"Diff1={d1}, r1:\n")
    console.print(r1, "\n")

    print(f"\nDiff2={d2}, r2:\n")
    console.print(r2)

    d3, r3 = show_diffblock("Hello, good world!", "Hello,  awesome world! ", "q1", "f1", "f2", 1,2)

    console.print(r3)
