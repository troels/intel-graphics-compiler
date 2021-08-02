#!/usr/bin/python3

#=========================== begin_copyright_notice ============================
#
# Copyright (C) 2021 Intel Corporation
#
# SPDX-License-Identifier: MIT
#
#============================ end_copyright_notice =============================

import argparse
import json


OUTPUT_HEADER = """// AUTOGENERATED FILE, DO NOT EDIT!
// Generated by GenerateTranslationCode.py script."""
# C++ declarations separator.
INTERVAL_BETWEEN_DECLS = "\n\n"
BUILTIN_PREFIX = "__cm_cl_"
# The name of the enum with operand kinds and the suffix of builtin operand
# kind arrays.
OPERAND_KIND = "OperandKind"
# The suffix of builtin operand name enums.
OPERAND_NAME = "Operand"

parser = argparse.ArgumentParser(
  description="Generate translation code from JSON description.")
parser.add_argument("--desc", required=True,
  help="JSON file with a description", metavar="<input>.json")
parser.add_argument("--output", required=True, help="output file",
  metavar="<output>.inc")

# Opens \p desc_filename JSON file and parses it.
# Parsed structures are returned.
def get_description_from_json(desc_filename):
  with open(desc_filename, "r") as desc_file:
    return json.load(desc_file)

# Generates:
# namespace name {
# enum Enum {
#   values[0],
#   values[1],
#   ...
# };
# } // namespace name
#
# The generated text is returned.
def generate_enum(name, values):
  text = "namespace {n} {{\nenum Enum {{\n".format(n=name)
  text += ",\n".join(["  {v}".format(v=value) for value in values])
  return text + "\n}};\n}} // namespace {n}".format(n=name)

# Generates:
# constexpr c_type name[] = {
#   values[0],
#   values[1],
#   ...
# };
#
# The generated text is returned.
def generate_array(c_type, name, values):
  assert values, "cannot generate an empty array"
  text = "constexpr {t} {n}[] = {{\n".format(t=c_type, n=name)
  text += ",\n".join(['  {v}'.format(v=value) for value in values])
  return text + "\n};"

# Generate enumerations that are not describing builtins but values of which
# are used to describe builtins.
def generate_helper_enums(helper_structures):
  return INTERVAL_BETWEEN_DECLS.join(
    [generate_enum(struct, helper_structures[struct])
      for struct in helper_structures])

def validate_builtin_desc(builtin_name, desc, helper_structures):
  if not all(operand["Kind"] in helper_structures[OPERAND_KIND]
               for operand in desc["Operands"]):
    raise RuntimeError("Some of {b} operand kinds is illegal because it's not "
                       "presented in OperandKind list".format(b=builtin_name))

# Raises an exception when some description inconsistency is found.
def validate_description(builtin_descs, helper_structures):
  for item in builtin_descs.items():
    validate_builtin_desc(*item, helper_structures)

# Returns a new list with additional "Size" element at the back.
def append_size(lst):
  return [*lst, "Size"]

# Generates an array with all the builtin names:
# costexpr const char* BuiltinNames[] = {
#   "__cm_cl_builtin0",
#   "__cm_cl_builtin1",
#   ...
# };
def generate_builtin_names_array(builtin_descs):
  return generate_array("const char*", "BuiltinNames",
                        ['"' + BUILTIN_PREFIX + desc["Name"] + '"'
                         for desc in builtin_descs.values()])

# Generates:
# namespace BuiltinOperand {
# enum Enum {
#   OperandName0,
#   OperandName1,
#   ...
# };
# } // namespace BuiltinOperand
def generate_operand_names_enum(builtin, desc):
  return generate_enum(
    builtin + OPERAND_NAME,
    append_size(operand["Name"] for operand in desc["Operands"]))

# Generates an enum for every builtin with its operands names to later use them
# as indices.
# Simplified output:
# enum Builtin0Operand { SRC };
# enum Builtin1Operand { DST, SRC };
# ...
def generate_operand_names_enums(builtin_descs):
  return INTERVAL_BETWEEN_DECLS.join(
    [generate_operand_names_enum(*builtin)
     for builtin in builtin_descs.items()])

# Generates an array with the number of operands for every builtin:
# constexpr int BuiltinOperandSize[] = {
#   Builtin0Operand::Size,
#   Builtin1Operand::Size,
#   ...
# };
def generate_operand_size_array(builtin_descs):
  return generate_array("int", "BuiltinOperandSize",
                        [builtin + OPERAND_NAME + "::Size"
                         for builtin in builtin_descs])

# Generates:
# constexpr OperandKind::Enum BuiltinOperandKind[] = {
#   OperandKind::Kind0,
#   OperandKind::Kind1,
#   ...
# };
def generate_operand_kinds_array(builtin, desc):
  return generate_array(OPERAND_KIND + "::Enum", builtin + OPERAND_KIND,
                        [OPERAND_KIND + "::" + operand["Kind"]
                         for operand in desc["Operands"]])

# Generates an array for every builtin with the list its operand kinds.
# Simplified output:
# constexpr OperandKind::Enum Builtin0OperandKind[] = {OperandKind::VectorIn};
# constexpr OperandKind::Enum Builtin1OperandKind[] = {
#   OperandKind::VectorOut, OperandKind::VectorIn};
def generate_operand_kinds_arrays(builtin_descs):
  return INTERVAL_BETWEEN_DECLS.join(
    generate_operand_kinds_array(builtin, desc)
      for builtin, desc in builtin_descs.items()
      if desc["Operands"])

# If there's an array of operand kinds, returns its name (array name degrades to
# pointer), otherwise returns nullptr. The can be operand kinds array if the
# builtin has no operands.
def get_operand_kinds_array_pointer(builtin, desc):
  if desc["Operands"]:
    return builtin + OPERAND_KIND
  return "nullptr"

# Generate an array of pointers to operand kinds arrays. So to get a kind of
# BuiltinN's M-th operand one can write BuiltinOperandKind[BuiltinN][M].
# Output:
# constexpr const OperandKind::Enum* BuiltinOperandKind[] = {
#   Builtin0OperandKind,
#   Builtin1OperandKind,
#   nullptr,
#   ...
# };
def generate_combined_operand_kinds_array(builtin_descs):
  return generate_array("const " + OPERAND_KIND + "::Enum*",
                        "Builtin" + OPERAND_KIND,
                        [get_operand_kinds_array_pointer(*builtin)
                         for builtin in builtin_descs.items()])

# Generate enums and arrays that describe CMCL builtins.
def generate_builtin_descriptions(builtin_descs):
  decls = [generate_enum("BuiltinID", append_size(builtin_descs.keys())),
           generate_builtin_names_array(builtin_descs),
           generate_operand_names_enums(builtin_descs),
           generate_operand_size_array(builtin_descs),
           generate_operand_kinds_arrays(builtin_descs),
           generate_combined_operand_kinds_array(builtin_descs)]
  return INTERVAL_BETWEEN_DECLS.join(decls)

# Generate output file text.
def get_generated_file(whole_desc):
  validate_description(whole_desc["BuiltinDescriptions"],
                       whole_desc["HelperStructures"])
  fragments = [OUTPUT_HEADER,
               generate_helper_enums(whole_desc["HelperStructures"]),
               generate_builtin_descriptions(whole_desc["BuiltinDescriptions"])]
  return INTERVAL_BETWEEN_DECLS.join(fragments)

args = parser.parse_args()
whole_desc = get_description_from_json(args.desc)
output_str = get_generated_file(whole_desc)
with open(args.output, "w") as output_file:
  output_file.write(output_str)