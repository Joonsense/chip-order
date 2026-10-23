# Makefile (Tiny Tapeout template, chip-lab order flow)
# make                 RTL simulation
# make GATES=yes       gate level (after the TT gds workflow, needs PDK_ROOT)
# make GATES=synth     Yosys generic netlist (synth.v from chip-lab)
SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = project.v

ifeq ($(GATES),yes)
SIM_BUILD				= sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DUSE_POWER_PINS
COMPILE_ARGS    += -DSIM
COMPILE_ARGS    += -DUNIT_DELAY=\#1
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v
else ifeq ($(GATES),synth)
SIM_BUILD				= sim_build/synth
VERILOG_SOURCES += $(PWD)/synth.v $(shell yosys-config --datdir)/simcells.v
else
SIM_BUILD				= sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
endif

COMPILE_ARGS 		+= -I$(SRC_DIR)
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb
COCOTB_TEST_MODULES = test

include $(shell cocotb-config --makefiles)/Makefile.sim
