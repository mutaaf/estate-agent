package com.acme.payments;

@RestController
public class ChargeController {
    @PostMapping("/v2/charge")
    public ChargeResponse charge(@RequestBody ChargeRequest req) { return svc.charge(req); }

    @GetMapping("/v2/refund/{id}")
    public Refund refund(@PathVariable String id) { return svc.refund(id); }

    @GetMapping("/internal/metrics")
    public Metrics metrics() { return svc.metrics(); }
}
