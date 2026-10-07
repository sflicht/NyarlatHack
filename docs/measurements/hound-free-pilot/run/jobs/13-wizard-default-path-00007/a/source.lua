return function(c)
  local s = c.state
  if not s then s = 0 end
  if s < 0 then s = 0 end
  if s > 1000000 then s = 0 end
  local h = c.history
  local n = 0
  if h then n = #h end
  local dx = 0
  local dy = 0
  if n >= 1 then
    local echo = h[1]
    local tx = echo.x
    local ty = echo.y
    local folded = false
    local still = false
    local vx = 0
    local vy = 0
    if n >= 2 then
      vx = h[2].x - h[1].x
      vy = h[2].y - h[1].y
      if vx == 0 and vy == 0 then still = true end
      if n >= 3 then
        local px = h[n].x - h[n - 1].x
        local py = h[n].y - h[n - 1].y
        if vx > 0 and px < 0 then folded = true
        elseif vx < 0 and px > 0 then folded = true
        elseif vy > 0 and py < 0 then folded = true
        elseif vy < 0 and py > 0 then folded = true end
      end
    end
    local phase = s % 4
    if still and phase == 1 then phase = 2 end
    if phase == 0 then
      if tx > c.mx then dx = 1
      elseif tx < c.mx then dx = -1 end
    elseif phase == 1 then
      if ty > c.my then dy = 1
      elseif ty < c.my then dy = -1 end
    elseif phase == 3 then
      if vx > 1 then vx = 1 elseif vx < -1 then vx = -1 end
      if vy > 1 then vy = 1 elseif vy < -1 then vy = -1 end
      if folded then
        vx = -vx
        vy = -vy
      end
      if vx ~= 0 then dx = vx
      elseif vy ~= 0 then dy = vy
      elseif tx > c.mx then dx = 1
      elseif tx < c.mx then dx = -1
      elseif ty > c.my then dy = 1
      elseif ty < c.my then dy = -1 end
    end
  end
  if dx > 1 then dx = 1 elseif dx < -1 then dx = -1 end
  if dy > 1 then dy = 1 elseif dy < -1 then dy = -1 end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  return {dx = dx, dy = dy, state = ns}
end
