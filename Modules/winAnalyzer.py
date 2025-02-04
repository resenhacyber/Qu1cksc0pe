#!/usr/bin/python3

import os
import re
import sys
import json
import warnings
import binascii
import subprocess

try:
    from rich import print
    from rich.table import Table
except:
    print("Error: >rich< module not found.")
    sys.exit(1)

try:
    import pefile as pf
except:
    print("Error: >pefile< module not found.")
    sys.exit(1)

try:
    warnings.filterwarnings("ignore")
    import clr
except:
    print("Error: >pythonnet< module not found.")
    print(f"[bold red]>>>[white] You can execute: [bold green]sudo apt install mono-complete && pip3 install pythonnet[white]")
    sys.exit(1)

#--------------------------------------------- Getting name of the file for statistics
fileName = str(sys.argv[1])

#--------------------------------------------- Legends
infoS = f"[bold cyan][[bold red]*[bold cyan]][white]"
errorS = f"[bold cyan][[bold red]![bold cyan]][white]"

#--------------------------------------------- Gathering Qu1cksc0pe path variable
sc0pe_path = open(".path_handler", "r").read()
# Using helper library
if os.path.exists("/usr/lib/python3/dist-packages/sc0pe_helper.py"):
    from sc0pe_helper import Sc0peHelper
    sc0pehelper = Sc0peHelper(sc0pe_path)
else:
    print(f"{errorS} [bold green]sc0pe_helper[white] library not installed. You need to execute [bold green]setup.sh[white] script!")
    sys.exit(1)

# Loading dnlib.dll
clr.AddReference(f"{sc0pe_path}/Systems/Windows/dnlib.dll")
from dnlib.DotNet import *
from System.IO import *

#--------------------------------------------------------------------- Keywords for categorized scanning
windows_api_list = json.load(open(f"{sc0pe_path}/Systems/Windows/windows_api_categories.json"))
dotnet_malware_pattern = json.load(open(f"{sc0pe_path}/Systems/Windows/dotnet_malware_patterns.json"))

#--------------------------------------------- Gathering all function imports from binary
pe = pf.PE(fileName)
allStrings = []
try:
    print(f"{infoS} Performing extraction of imports...")
    binaryfile = pf.PE(fileName)
    for imps in binaryfile.DIRECTORY_ENTRY_IMPORT:
        try:
            for im in imps.imports:
                allStrings.append([im.name.decode("ascii"), hex(binaryfile.OPTIONAL_HEADER.ImageBase + im.address)]) # For full address and not only offset
        except:
            continue
except:
    print(f"{infoS} Performing extraction of imports via [bold green]HEX read+regex[white] style...")
    binary_data = open(fileName, "rb").read()
    for categ in windows_api_list:
        for api in windows_api_list[categ]["apis"]:
            try:
                matcher = re.finditer(api.encode(), binary_data, re.IGNORECASE)
                for pos in matcher:
                    allStrings.append([api, hex(pos.start())])
            except:
                continue

# Get exports
try:
    binaryfile = pf.PE(fileName)
    for exp in binaryfile.DIRECTORY_ENTRY_EXPORT.symbols:
        try:
            allStrings.append([exp.name.decode('utf-8'), hex(binaryfile.OPTIONAL_HEADER.ImageBase + exp.address)]) # For full address and not only offset

        except:
            continue
except:
    pass

#--------------------------------------------- Dictionary of Categories
dictCateg = {
    "Registry": [],
    "File": [],
    "Networking/Web": [],
    "Keyboard/Keylogging": [],
    "Process": [],
    "Memory Management": [],
    "Dll/Resource Handling": [],
    "Evasion/Bypassing": [],
    "System/Persistence": [],
    "COMObject": [],
    "Cryptography": [],
    "Information Gathering": [],
    "Other/Unknown": []
}

#------------------------------------ Report structure
winrep = {
    "filename": "",
    "timedatestamp": "",
    "hash_md5": "",
    "hash_sha1": "",
    "hash_sha256": "",
    "imphash": "",
    "all_imports": 0,
    "categorized_imports": 0,
    "categories": {},
    "matched_rules": [],
    "linked_dll": [],
    "sections": {}
}

#------------------------------------ Defining function
class WindowsAnalyzer:
    def __init__(self, target_file):
        self.target_file = target_file
        self.allFuncs = 0
        self.import_indicator = 0
        self.executable_buffer = open(self.target_file, "rb").read()
        self.all_strings = open(f"{sc0pe_path}/temp.txt", "r").read().split("\n")
        self.exec_type = subprocess.run(["file", self.target_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ".Net" in self.exec_type.stdout.decode():
            self.dotnet_file_analyzer()
            sys.exit(0)

    def api_categorizer(self):
        for win_api in allStrings:
            for key in windows_api_list:
                if win_api[0] in windows_api_list[key]["apis"]:
                    if win_api[0] != "":
                        windows_api_list[key]["occurence"] += 1
                        dictCateg[key].append(win_api)
                        self.allFuncs += 1

    def dictcateg_parser(self):
        for key in dictCateg:
            if dictCateg[key] != []:
                # More important categories
                if key == "Keyboard/Keylogging" or key == "Evasion/Bypassing" or key == "System/Persistence" or key == "Cryptography" or key == "Information Gathering":
                    tables = Table(title="* WARNING *", title_style="blink italic yellow", title_justify="center", style="yellow")
                else:
                    tables = Table()
                
                # Printing zone
                tables.add_column(f"Functions or Strings about [bold green]{key}", justify="center")
                tables.add_column("Address", justify="center")
                winrep["categories"].update({key: []})
                for func in dictCateg[key]:
                    if func[0] == "":
                        pass
                    else:
                        tables.add_row(f"[bold red]{func[0]}", f"[bold red]{func[1]}")
                        winrep["categories"][key].append(func[0])
                        self.import_indicator += 1
                print(tables)

        # If there is no function imported in target executable
        if self.import_indicator == 0:
            print("[bold white on red]There is no function/API imports found.")
            print("[magenta]>>[white] Try [bold green][i]--packer[/i] [white]or [bold green][i]--lang[/i] [white]to see additional info about target file.\n")

    def dll_files(self):
        try:
            dllTable = Table()
            dllTable.add_column("Linked DLL Files", style="bold green", justify="center")
            for items in binaryfile.DIRECTORY_ENTRY_IMPORT:
                dlStr = str(items.dll.decode())
                dllTable.add_row(f"{dlStr}", style="bold red")
                winrep["linked_dll"].append(dlStr)
            print(dllTable)
        except:
            pass

    def gather_timestamp(self):
        mydict = pe.dump_dict()
        tempstr = mydict["FILE_HEADER"]["TimeDateStamp"]["Value"][11:].replace("[", "")
        datestamp = tempstr.replace("]", "")
        return datestamp

    def scan_for_special_artifacts(self):
        switch = 0
        print(f"\n{infoS} Performing special artifact detection. Please wait...")
        spec_table = Table()
        spec_table.add_column("[bold green]Artifact Names", justify="center")
        spec_table.add_column("[bold green]Patterns", justify="center")
        spec_table.add_column("[bold green]Occurence", justify="center")
        special = json.load(open(f"{sc0pe_path}/Systems/Multiple/special_artifact_patterns.json"))
        for spec in special:
            for pat in special[spec]["patterns"]:
                ofs = re.findall(pat.encode(), self.executable_buffer)
                if ofs != []:
                    spec_table.add_row(spec, pat, str(len(ofs)))
                    switch += 1
        if switch != 0:
            print(spec_table)
        else:
            print(f"{errorS} There is no special artifact pattern found!\n")

    def check_for_valid_registry_keys(self):
        print(f"\n{infoS} Looking for: [bold green]Windows Registry Key[white]")
        # Defining table and patterns
        reg_table = Table()
        reg_table.add_column("[bold green]Registry Keys", justify="center")
        reg_key_array = [r"SOFTWARE\\[A-Za-z0-9_\\]*", r"HKCU_[A-Za-z0-9_\\]*", r"HKLM_[A-Za-z0-9_\\]*", r"SYSTEM\\[A-Za-z0-9_\\]*"]

        # Array for holding keys
        registry_keys = []

        # Search for keys in file buffer
        for key in reg_key_array:
            chk = re.findall(key, str(self.all_strings), re.IGNORECASE) # "re.IGNORECASE" in case of non case sensitive values
            if chk != []:
                for pattern in chk:
                    if len(pattern) > 10 and pattern not in registry_keys:
                        registry_keys.append(pattern)
        # Print output
        if registry_keys != []:
            for reg in registry_keys:
                reg_table.add_row(reg)
            print(reg_table)
        else:
            print(f"{errorS} There is no pattern about registry keys!\n")

    def check_for_interesting_stuff(self):
        print(f"\n{infoS} Looking for: [bold green]Interesting String Patterns[white]")
        # Defining table and patterns
        stuff_table = Table()
        stuff_table.add_column("[bold green]Interesting Patterns", justify="center")
        interesting_stuff = [
            r"[a-zA-Z0-9_.]*pdb", r"[a-zA-Z0-9_.]*vbs", 
            r"[a-zA-Z0-9_.]*vba", r"[a-zA-Z0-9_.]*vbe", 
            r"[a-zA-Z0-9_.]*exe", r"[a-zA-Z0-9_.]*ps1",
            r"[a-zA-Z0-9_.]*dll", r"[a-zA-Z0-9_.]*bat",
            r"[a-zA-Z0-9_.]*cmd", r"[a-zA-Z0-9_.]*tmp",
            r"[a-zA-Z0-9_.]*dmp", r"[a-zA-Z0-9_.]*cfg",
            r"[a-zA-Z0-9_.]*lnk", r"[a-zA-Z0-9_.]*config",
            r"[a-zA-Z0-9_.]*7z", r"[a-zA-Z0-9_.]*docx"
            r"SeLockMemoryPrivilege", r"SeShutdownPrivilege",
            r"SeChangeNotifyPrivilege", r"SeUndockPrivilege",
            r"SeIncreaseWorkingSetPrivilege", r"SeTimeZonePrivilege"
        ]

        # Array for holding string values
        intstf = []

        # Search for keys in file buffer
        for key in interesting_stuff:
            chk = re.findall(key, str(self.all_strings), re.IGNORECASE) # "re.IGNORECASE" in case of non case sensitive values
            if chk != []:
                for pattern in chk:
                    if pattern not in intstf:
                        intstf.append(pattern)

        # Print output
        if intstf != []:
            for stf in intstf:
                if "Se" in stf and "Privilege" in stf:
                    stuff_table.add_row(f"[bold red]{stf}[white]")
                else:
                    stuff_table.add_row(stf)
            print(stuff_table)
        else:
            print(f"{errorS} There is no pattern about interesting string values!\n")

    def detect_embedded_PE(self):
        print(f"\n{infoS} Performing embedded PE file detection...")
        mz_header = "4D5A9000"
        valid_offsets = []
        matches = re.finditer(binascii.unhexlify(mz_header), self.executable_buffer)
        for pos in matches:
            if pos.start() != 0:
                valid_offsets.append(pos.start())
        if valid_offsets != []:
            print(f"{infoS} There is possible [bold red]{len(valid_offsets)}[white] embedded PE file found!")
            print(f"{infoS} Execute: [bold green]python3 qu1cksc0pe.py --file {fileName} --sigcheck[white] to extract them!\n")
        else:
            print(f"{errorS} There is no embedded PE file!\n")

    def section_parser(self):
        peStatistics = Table(title="* Informations About Sections *", title_style="bold italic cyan", title_justify="center")
        peStatistics.add_column("Section Name", justify="center")
        peStatistics.add_column("Virtual Size", justify="center")
        peStatistics.add_column("Virtual Address", justify="center")
        peStatistics.add_column("Size Of Raw Data", justify="center")
        peStatistics.add_column("Pointer to Raw Data", justify="center")
        peStatistics.add_column("Entropy", justify="center")

        # Parsing sections
        for sect in pe.sections:
            try:
                if sect.get_entropy() >= 7:
                    peStatistics.add_row(
                        str(sect.Name.decode().rstrip('\x00')),
                        f"{hex(sect.Misc_VirtualSize)}",
                        f"{hex(sect.VirtualAddress)}",
                        f"{hex(sect.SizeOfRawData)}",
                        f"{hex(sect.PointerToRawData)}",
                        f"[bold red]{sect.get_entropy()} [i]Possible obfuscation!![/i]"
                    )
                else:
                    peStatistics.add_row(
                        str(sect.Name.decode().rstrip('\x00')),
                        f"{hex(sect.Misc_VirtualSize)}",
                        f"{hex(sect.VirtualAddress)}",
                        f"{hex(sect.SizeOfRawData)}",
                        f"{hex(sect.PointerToRawData)}",
                        str(sect.get_entropy())
                    )
                winrep["sections"].update(
                    {
                        str(sect.Name.decode().rstrip('\x00')):
                        {
                            "virtualsize": hex(sect.Misc_VirtualSize),
                            "virtualaddress": hex(sect.VirtualAddress),
                            "sizeofrawdata": hex(sect.SizeOfRawData),
                            "pointertorawdata": hex(sect.PointerToRawData),
                            "entropy": str(sect.get_entropy())
                        }
                    }
                )
            except:
                continue
        print(peStatistics)

    def statistics_method(self):
        datestamp = self.gather_timestamp()
        print(f"\n[bold green]-> [white]Statistics for: [bold green][i]{self.target_file}[/i]")
        print(f"[bold magenta]>>[white] Time Date Stamp: [bold green][i]{datestamp}[/i]")
        winrep["filename"] = self.target_file
        winrep["timedatestamp"] = datestamp
        sc0pehelper.hash_calculator(self.target_file, winrep)
        print(f"[bold magenta]>>[white] IMPHASH: [bold green]{binaryfile.get_imphash()}")
        winrep["imphash"] = binaryfile.get_imphash()

        # printing all function statistics
        statistics = Table()
        statistics.add_column("Categories", justify="center")
        statistics.add_column("Number of Functions or Strings", justify="center")
        statistics.add_row("[bold green][i]All Imports,Exports[/i]", f"[bold green]{len(allStrings)}")
        statistics.add_row("[bold green][i]Categorized Imports[/i]", f"[bold green]{self.allFuncs}")
        winrep["all_imports_exports"] = len(allStrings)
        winrep["categorized_imports"] = self.allFuncs
        for key in windows_api_list:
            if windows_api_list[key]["occurence"] == 0:
                pass
            else:
                if key == "Keyboard/Keylogging" or key == "Evasion/Bypassing" or key == "System/Persistence" or key == "Cryptography" or key == "Information Gathering":
                    statistics.add_row(f"[bold yellow]{key}", f"[bold red]{windows_api_list[key]['occurence']}")
                else:
                    statistics.add_row(key, str(windows_api_list[key]["occurence"]))
        print(statistics)

        # Warning about obfuscated file
        if self.allFuncs < 20:
            print("[bold white on red]This file might be obfuscated or encrypted. [white]Try [bold green][i]--packer[/i] [white]to scan this file for packers.")
            print("[bold]You can also use [green][i]--hashscan[/i] [white]to scan this file.")
            sys.exit(0)

    def dotnet_file_analyzer(self):
        print(f"{infoS} Performing .NET analysis...")

        # Load the assembly using dnlib
        assembly = AssemblyDef.Load(self.target_file)

        class_names = []
        blacklisted = ["AES_Decrypt", "AntiVM", "Decrypt", "GetResource",
                       "ReadProcessMemory", "WriteProcessMemory",
                       "SetKernelObjectSecurity", "VirtualAllocEx", "MSHTMLHost"
                    ]
        for module in assembly.Modules:
            for typ in module.Types:
                if "<" not in typ.FullName:
                    class_names.append(typ.FullName)
                    dotnet_table = Table()
                    dotnet_table.add_column(f"Methods in Class: [bold green]{typ.FullName}[white]", justify="center")
                    methodz = []
                    for met in typ.Methods:
                        if str(met.Name) not in methodz:
                            methodz.append(str(met.Name))
                            if str(met.Name) in blacklisted:
                                dotnet_table.add_row(f"[bold red]{str(met.Name)}[white]")
                            else:
                                dotnet_table.add_row(str(met.Name))
                    print(dotnet_table)

        print(f"\n{infoS} Performing pattern analysis...")
        fswc = 0
        dot_fam = Table()
        dot_fam.add_column(f"[bold green]Malware Family/Artifact", justify="center")
        dot_fam.add_column(f"[bold green]Pattern Occurence", justify="center")
        for family in dotnet_malware_pattern:
            for dotp in dotnet_malware_pattern[family]["patterns"]:
                matcher = re.findall(dotp, str(class_names), re.IGNORECASE)
                if matcher != []:
                    dotnet_malware_pattern[family]["occurence"] += len(matcher)
            if dotnet_malware_pattern[family]["occurence"] != 0:
                dot_fam.add_row(family, str(dotnet_malware_pattern[family]["occurence"]))
                fswc += 1
        if fswc != 0:
            print(dot_fam)
        else:
            print(f"{errorS} Couldn\'t detect any pattern. This file might be obfuscated!\n")

        self.check_for_valid_registry_keys()
        self.check_for_interesting_stuff()

# Execute
windows_analyzer = WindowsAnalyzer(target_file=fileName)
windows_analyzer.api_categorizer()
windows_analyzer.dictcateg_parser()
windows_analyzer.dll_files()
windows_analyzer.scan_for_special_artifacts()
windows_analyzer.check_for_valid_registry_keys()
windows_analyzer.check_for_interesting_stuff()
windows_analyzer.detect_embedded_PE()

# Yara rule match
print(f"\n{infoS} Performing YARA rule matching...")
sc0pehelper.yara_rule_scanner("windows", fileName, config_path=f"{sc0pe_path}/Systems/Windows/windows.conf", report_object=winrep)

windows_analyzer.section_parser()
windows_analyzer.statistics_method()

# Print reports
if sys.argv[2] == "True":
    sc0pehelper.report_writer("windows", winrep)