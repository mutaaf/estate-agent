package com.acme.payments;

public class LedgerClient {
    private final LedgerGrpc.LedgerBlockingStub stub =
        LedgerGrpc.newBlockingStub(channel);
}
