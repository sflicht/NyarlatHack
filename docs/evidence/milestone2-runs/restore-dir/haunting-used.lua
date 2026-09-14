-- Hand-authored first haunting. History is oldest first; target three observations back.
return function(c)
    local index = #c.history - 3
    if index < 1 then index = 1 end
    local point = c.history[index]
    local dx, dy = 0, 0
    if point.x > c.mx then dx = 1 elseif point.x < c.mx then dx = -1 end
    if point.y > c.my then dy = 1 elseif point.y < c.my then dy = -1 end
    return {dx=dx, dy=dy, state=(c.state+1)%1000001}
end
