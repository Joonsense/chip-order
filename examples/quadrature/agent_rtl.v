module tt_um_joonsense_quadrature (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    reg [1:0] sync1;
    reg [1:0] sync2;
    reg [1:0] prev;
    reg [7:0] count;
    reg       err;

    // Gray state (B<<1)|A to position index in the forward sequence 0,1,3,2
    wire [1:0] idx_cur  = {sync2[1], sync2[1] ^ sync2[0]};
    wire [1:0] idx_prev = {prev[1],  prev[1]  ^ prev[0]};
    wire [1:0] step     = idx_cur - idx_prev;

    always @(posedge clk) begin
        if (!rst_n) begin
            sync1 <= 2'b00;
            sync2 <= 2'b00;
            prev  <= 2'b00;
            count <= 8'h00;
            err   <= 1'b0;
        end else begin
            if (uio_in[0]) begin
                count <= 8'h00;
                err   <= 1'b0;
            end else begin
                case (step)
                    2'd1:    count <= count + 8'd1;
                    2'd3:    count <= count - 8'd1;
                    2'd2:    err   <= 1'b1;
                    default: ;
                endcase
            end
            prev  <= sync2;
            sync2 <= sync1;
            sync1 <= ui_in[1:0];
        end
    end

    assign uo_out  = count;
    assign uio_out = {err, 7'b0000000};
    assign uio_oe  = 8'h80;

    wire _unused = &{ena, ui_in[7:2], uio_in[7:1], 1'b0};

endmodule
