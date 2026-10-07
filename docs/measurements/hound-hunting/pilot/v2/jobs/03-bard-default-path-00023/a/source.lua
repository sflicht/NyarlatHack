return function(c)
  -- Flat section: hold every fifth beat; on beat 2 the prior edge, else the newest line.
  local s=(c.state+1)%1000001
  if s%5==0 then
    return {dx=0,dy=0,state=s}
  end
  local h=c.history
  local n=0
  local i=1
  while i<=8 do
    if h[i]==nil then break end
    n=i
    i=i+1
  end
  if n<1 then
    return {dx=0,dy=0,state=s}
  end
  local idx=n
  if n>1 and s%5==2 then idx=n-1 end
  local t=h[idx]
  local dx=0
  local dy=0
  if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
  if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
  return {dx=dx,dy=dy,state=s}
end
