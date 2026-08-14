public void ConfigureServices(IServiceCollection services)
{
    services.AddHttpClient("payments-api", c => {
        c.BaseAddress = new Uri("https://payments-api.internal");
    });
}
