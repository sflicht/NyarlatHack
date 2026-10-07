return function(c)
  local s=c.state+1
  if s>1000000 then s=0 end
  local h=c.history
  local echo=h[1]
  local dx=0
  local dy=0
  if echo~=nil and (s%3)~=0 then
    local ex=echo.x-c.mx
    local ey=echo.y-c.my
    local ax=ex
    local ay=ey
    if ax<0 then ax=-ax end
    if ay<0 then ay=-ay end
    if ax>ay then
      if ex>0 then dx=1 elseif ex<0 then dx=-1 end
    elseif ay>ax then
      if ey>0 then dy=1 elseif ey<0 then dy=-1 end
    elseif ex>=0 then
      dx=1
    else
      dx=-1
    end
    local face=h[8]
    if face==nil then face=h[7] end
    if face==nil then face=h[6] end
    if face==nil then face=h[5] end
    if face==nil then face=h[4] end
    if face==nil then face=h[3] end
    if face==nil then face=h[2] end
    if face==nil then face=h[1] end
    if face~=nil and (c.mx+dx)==face.x and (c.my+dy)==face.y then
      if dx~=0 then dx=-dx else dy=-dy end
    end
  end
  return {dx=dx,dy=dy,state=s}
end
