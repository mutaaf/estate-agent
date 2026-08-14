function fetchCharge() as Object
    transfer = CreateObject("roUrlTransfer")
    transfer.SetUrl("https://payments-api.internal/v2/charge")
    return transfer.GetToString()
end function
