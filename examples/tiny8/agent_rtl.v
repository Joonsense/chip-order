module tt_um_joonsense_tiny8 (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    reg [7:0] mem [0:15];
    reg [7:0] acc;
    reg [7:0] outr;
    reg [3:0] pc;
    reg [3:0] ptr;
    reg       halted;

    wire [7:0] ins = mem[pc];
    wire [3:0] op  = ins[7:4];
    wire [3:0] a   = ins[3:0];
    wire [7:0] m   = mem[a];
    wire       accz = (acc == 8'd0);

    assign uo_out  = outr;
    assign uio_out = {pc, halted, 3'b000};
    assign uio_oe  = 8'hF8;

    wire _unused = &{ena, uio_in[7:3], 1'b0};

    integer i;
    always @(posedge clk) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1) mem[i] <= 8'd0;
            acc    <= 8'd0;
            outr   <= 8'd0;
            pc     <= 4'd0;
            ptr    <= 4'd0;
            halted <= 1'b0;
        end else if (uio_in[2]) begin
            pc     <= 4'd0;
            ptr    <= 4'd0;
            halted <= 1'b0;
        end else if (uio_in[0]) begin
            mem[ptr] <= ui_in;
            ptr      <= ptr + 4'd1;
        end else if (uio_in[1] && !halted) begin
            pc <= pc + 4'd1;
            case (op)
                4'h1: acc <= {4'd0, a};
                4'h2: acc <= m;
                4'h3: mem[a] <= acc;
                4'h4: acc <= acc + m;
                4'h5: acc <= acc - m;
                4'h6: acc <= acc & m;
                4'h7: acc <= acc | m;
                4'h8: acc <= acc ^ m;
                4'h9: acc <= {acc[6:0], 1'b0};
                4'hA: acc <= {1'b0, acc[7:1]};
                4'hB: pc <= a;
                4'hC: if (accz) pc <= a;
                4'hD: if (!accz) pc <= a;
                4'hE: outr <= acc;
                4'hF: begin
                    halted <= 1'b1;
                    pc     <= pc;
                end
                default: ;
            endcase
        end
    end
endmodule
