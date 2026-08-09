// C# separates a using directive from a using statement, and only the
// directive is an import. Getting this wrong hides real code from duplicate
// detection, which is how it was found.
using System;
using System.IO;
using Alias = System.Collections.Generic.List<int>;

namespace Fixture
{
    public class Reader
    {
        public string Read(string path)
        {
            using var stream = File.OpenRead(path);
            using (var other = File.OpenRead(path))
            {
                var buffer = new byte[16];
                _ = other.Read(buffer, 0, buffer.Length);
            }
            using FileStream third = File.OpenRead(path);
            var list = new Alias();
            list.Add(stream.ReadByte());
            Console.WriteLine(third.Length);
            return path;
        }
    }
}
